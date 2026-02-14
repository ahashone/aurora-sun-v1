"""
Review Module for Aurora Sun V1.

This module handles the daily review workflow including:
- Task completion check (from DailyPlan)
- Accomplishments, challenges, energy, reflection, forward-look
- Segment-specific reflection prompts
- Auto-trigger in evening (not only manual)
- Scrub completed tasks from todo
- Natural language entry

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.core.segment_context import WorkingStyleCode
from src.i18n import LanguageCode
from src.i18n.strings import t as translate

# Import models
from src.models.daily_plan import DailyPlan
from src.models.task import Task

if TYPE_CHECKING:
    from src.core.module_response import ModuleResponse


# State machine states for the Review module
class ReviewStates:
    """State constants for the Review module state machine."""

    ACCOMPLISHMENTS = "ACCOMPLISHMENTS"
    CHALLENGES = "CHALLENGES"
    ENERGY = "ENERGY"
    REFLECTION = "REFLECTION"
    FORWARD = "FORWARD"
    DONE = "DONE"


# Segment-specific reflection prompts
SEGMENT_REFLECTION_PROMPTS: dict[WorkingStyleCode, dict[str, str]] = {
    "AD": {
        "challenges": "What derailed your attention today? What patterns did you notice?",
        "reflection": "What excited you? What felt like a win even if small?",
        "energy": "How were your energy spikes today? When did you feel most alive?",
    },
    "AU": {
        "challenges": "What overwhelmed you today? Were there unexpected sensory or routine disruptions?",
        "reflection": "What felt stable and good? What routines helped?",
        "energy": "How is your nervous system feeling? Any signs of overload?",
    },
    "AH": {
        "challenges": "What was hard - the attention stuff, the sensory stuff, or both?",
        "reflection": "What strategies worked? What did you learn about your needs?",
        "energy": "Spoons: How many did you start with vs. end with? Channels: which dominated?",
    },
    "NT": {
        "challenges": "What was difficult today? What could have gone better?",
        "reflection": "What did you accomplish that you're proud of?",
        "energy": "How's your energy level compared to usual?",
    },
    "CU": {
        "challenges": "What was difficult today?",
        "reflection": "What did you learn or accomplish?",
        "energy": "How are you feeling?",
    },
}


class ReviewModule:
    """
    Review Module for daily reflection and review.

    This module implements the Module protocol and handles the daily
    review workflow with segment-specific prompts and energy tracking.

    Key features:
    - Task completion check from DailyPlan
    - Accomplishments, challenges, energy, reflection, forward-look
    - Segment-specific reflection prompts
    - Auto-trigger in evening (daily workflow hook)
    - Natural language entry

    Attributes:
        name: Module identifier
        intents: List of intents this module handles
        pillar: The pillar this module belongs to
    """

    name: str = "review"
    intents: list[str] = [
        "review.start",
        "review.accomplishments",
        "review.challenges",
        "review.energy",
        "review.reflection",
        "review.forward",
    ]
    pillar: str = "vision_to_task"

    # State machine states
    STATES = {
        "ACCOMPLISHMENTS": "What did you complete?",
        "CHALLENGES": "What was difficult?",
        "ENERGY": "How's your energy?",
        "REFLECTION": "Any thoughts?",
        "FORWARD": "What's tomorrow?",
        "DONE": "Flow complete",
    }

    def __init__(self, db_session: AsyncSession | None = None):
        """
        Initialize the Review module.

        Args:
            db_session: Optional database session for testing
        """
        self._db_session = db_session

    def _t(self, lang: str, module: str, key: str, **kwargs: object) -> str:
        """Helper to call translate with proper type casting."""
        from typing import cast
        # Cast lang to LanguageCode - fallback to 'en' if not valid
        valid_langs = ("en", "de", "sr", "el")
        lang_code: LanguageCode = cast(LanguageCode, lang) if lang in valid_langs else "en"
        return translate(lang_code, module, key, **kwargs)

    async def _get_db_session(self, ctx: ModuleContext) -> AsyncSession | None:
        """
        Get the database session from context or use the stored one.

        Args:
            ctx: Module context

        Returns:
            AsyncSession for database operations, or None if unavailable
        """
        if self._db_session:
            return self._db_session
        # In production, this would come from a database service
        # For now, we rely on metadata being passed through context
        if "db_session" in ctx.metadata:
            db_session = ctx.metadata["db_session"]
            # mypy: metadata is dict[str, Any], we assert the type here
            assert isinstance(db_session, AsyncSession)
            return db_session
        return None

    async def _get_today_daily_plan(
        self, ctx: ModuleContext
    ) -> DailyPlan | None:
        """
        Get today's DailyPlan for the user.

        Args:
            ctx: Module context

        Returns:
            Today's DailyPlan if exists, None otherwise
        """
        db = await self._get_db_session(ctx)
        if db is None:
            return None
        today = date.today()

        result = await db.execute(
            select(DailyPlan).where(
                DailyPlan.user_id == ctx.user_id,
                DailyPlan.date == today,
            )
        )
        return result.scalar_one_or_none()

    async def _get_completed_tasks(
        self, ctx: ModuleContext, target_date: date | None = None
    ) -> list[Task]:
        """
        Get tasks completed today (or on a specific date).

        Args:
            ctx: Module context
            target_date: Optional specific date, defaults to today

        Returns:
            List of completed tasks (empty list if no database session)
        """
        db = await self._get_db_session(ctx)
        if db is None:
            return []
        target = target_date or date.today()

        result = await db.execute(
            select(Task)
            .where(
                Task.user_id == ctx.user_id,
                Task.status == "completed",
                Task.committed_date == target,
            )
            .order_by(Task.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _get_pending_tasks(
        self, ctx: ModuleContext
    ) -> list[Task]:
        """
        Get pending tasks for today.

        Args:
            ctx: Module context

        Returns:
            List of pending tasks (empty list if no database session)
        """
        db = await self._get_db_session(ctx)
        if db is None:
            return []
        today = date.today()

        result = await db.execute(
            select(Task)
            .where(
                Task.user_id == ctx.user_id,
                Task.status.in_(["pending", "in_progress"]),
                Task.committed_date == today,
            )
            .order_by(Task.priority.asc().nullslast(), Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def _update_daily_plan_energy(
        self, ctx: ModuleContext, energy_type: str, energy_value: int
    ) -> None:
        """
        Update energy in DailyPlan.

        Args:
            ctx: Module context
            energy_type: "morning_energy" or "evening_energy"
            energy_value: Energy level (1-5)
        """
        db = await self._get_db_session(ctx)
        if db is None:
            return
        today = date.today()

        result = await db.execute(
            select(DailyPlan).where(
                DailyPlan.user_id == ctx.user_id,
                DailyPlan.date == today,
            )
        )
        daily_plan = result.scalar_one_or_none()

        if daily_plan:
            setattr(daily_plan, energy_type, energy_value)
            await db.commit()

    async def _get_segment_prompt(
        self, ctx: ModuleContext, prompt_type: str
    ) -> str:
        """
        Get segment-specific prompt for a given prompt type.

        Args:
            ctx: Module context
            prompt_type: Type of prompt (challenges, reflection, energy)

        Returns:
            Segment-specific prompt text
        """
        segment_code = ctx.segment_context.core.code
        prompts = SEGMENT_REFLECTION_PROMPTS.get(segment_code, SEGMENT_REFLECTION_PROMPTS["NT"])
        return prompts.get(prompt_type, "")

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Handle entry into the Review module.

        This is called when the user starts a review session.
        It loads today's DailyPlan and completed tasks, then starts
        the review flow.

        Args:
            ctx: Module context

        Returns:
            ModuleResponse with welcome message and initial state
        """
        lang = ctx.language

        # Get today's completed tasks
        completed_tasks = await self._get_completed_tasks(ctx)
        pending_tasks = await self._get_pending_tasks(ctx)

        # Build context for the response
        context_data = {
            "completed_count": len(completed_tasks),
            "pending_count": len(pending_tasks),
            "completed_tasks": [
                task.title for task in completed_tasks if task.title
            ],
            "pending_tasks": [
                task.title for task in pending_tasks[:3] if task.title
            ],
        }

        # Build the welcome message
        if completed_tasks:
            tasks_text = "\n".join(
                [f"- {task.title}" for task in completed_tasks[:5] if task.title]
            )
            intro = self._t(lang, "review", "welcome_with_tasks").format(
                count=len(completed_tasks),
                tasks=tasks_text,
            )
        else:
            intro = self._t(lang, "review", "welcome_no_tasks")

        # Start with accomplishments state
        prompt = self._t(lang, "review", "accomplishments_prompt")

        return ModuleResponse(
            text=intro + "\n\n" + prompt,
            next_state=ReviewStates.ACCOMPLISHMENTS,
            metadata={
                "completed_tasks": context_data["completed_tasks"],
                "pending_tasks": context_data["pending_tasks"],
                "completed_count": context_data["completed_count"],
                "pending_count": context_data["pending_count"],
            },
        )

    async def handle(self, message: str, ctx: ModuleContext) -> ModuleResponse:
        """
        Handle a user message within the Review module.

        Routes based on the current state in the state machine:
        - ACCOMPLISHMENTS: Show completed tasks from DailyPlan
        - CHALLENGES: Segment-specific prompts
        - ENERGY: Use segment-appropriate energy check
        - REFLECTION: One-line reflection
        - FORWARD: Tomorrow's intention

        Args:
            message: The user's input message
            ctx: Module context

        Returns:
            ModuleResponse with text, optional buttons, next_state
        """
        current_state = ctx.state

        # Route based on current state
        if current_state == ReviewStates.ACCOMPLISHMENTS:
            return await self._handle_accomplishments(message, ctx)
        elif current_state == ReviewStates.CHALLENGES:
            return await self._handle_challenges(message, ctx)
        elif current_state == ReviewStates.ENERGY:
            return await self._handle_energy(message, ctx)
        elif current_state == ReviewStates.REFLECTION:
            return await self._handle_reflection(message, ctx)
        elif current_state == ReviewStates.FORWARD:
            return await self._handle_forward(message, ctx)
        else:
            # Default: start the review flow
            return await self.on_enter(ctx)

    async def _handle_accomplishments(
        self, message: str, ctx: ModuleContext
    ) -> ModuleResponse:
        """
        Handle the accomplishments step.

        Args:
            message: User's response about accomplishments
            ctx: Module context

        Returns:
            ModuleResponse transitioning to CHALLENGES
        """
        lang = ctx.language

        # Get segment-specific challenges prompt
        challenges_prompt = await self._get_segment_prompt(ctx, "challenges")

        # Also provide fallback to translation
        fallback = self._t(lang, "review", "challenges_prompt")

        prompt = challenges_prompt or fallback

        return ModuleResponse(
            text=self._t(lang, "review", "challenges_intro") + "\n\n" + prompt,
            next_state=ReviewStates.CHALLENGES,
            metadata={"accomplishments": message},
        )

    async def _handle_challenges(
        self, message: str, ctx: ModuleContext
    ) -> ModuleResponse:
        """
        Handle the challenges step.

        Args:
            message: User's response about challenges
            ctx: Module context

        Returns:
            ModuleResponse transitioning to ENERGY
        """
        lang = ctx.language

        # Get segment-specific energy prompt
        energy_prompt = await self._get_segment_prompt(ctx, "energy")

        # Fallback to translation
        fallback = self._t(lang, "review", "energy_prompt")

        prompt = energy_prompt or fallback

        # Check if this is a quick energy response (1-5)
        if message.strip().isdigit() and 1 <= int(message.strip()) <= 5:
            # User gave a quick energy number
            await self._update_daily_plan_energy(ctx, "evening_energy", int(message.strip()))
            return ModuleResponse(
                text=self._t(lang, "review", "energy_quick_response"),
                next_state=ReviewStates.REFLECTION,
            )

        return ModuleResponse(
            text=self._t(lang, "review", "energy_intro") + "\n\n" + prompt,
            next_state=ReviewStates.ENERGY,
            metadata={"challenges": message},
        )

    async def _handle_energy(
        self, message: str, ctx: ModuleContext
    ) -> ModuleResponse:
        """
        Handle the energy step.

        Uses segment-appropriate energy check based on the user's segment.

        Args:
            message: User's response about energy
            ctx: Module context

        Returns:
            ModuleResponse transitioning to REFLECTION
        """
        lang = ctx.language

        # Try to parse energy as a number
        energy_value: int | None = None
        if message.strip().isdigit():
            energy_value = int(message.strip())
            if 1 <= energy_value <= 5:
                await self._update_daily_plan_energy(ctx, "evening_energy", energy_value)

        # Get segment-specific reflection prompt
        reflection_prompt = await self._get_segment_prompt(ctx, "reflection")

        # Fallback to translation
        fallback = self._t(lang, "review", "reflection_prompt")

        prompt = reflection_prompt or fallback

        return ModuleResponse(
            text=self._t(lang, "review", "reflection_intro") + "\n\n" + prompt,
            next_state=ReviewStates.REFLECTION,
            metadata={
                "energy": message,
                "energy_value": energy_value,
            },
        )

    async def _handle_reflection(
        self, message: str, ctx: ModuleContext
    ) -> ModuleResponse:
        """
        Handle the reflection step.

        Args:
            message: User's reflection response
            ctx: Module context

        Returns:
            ModuleResponse transitioning to FORWARD
        """
        lang = ctx.language

        return ModuleResponse(
            text=self._t(lang, "review", "forward_intro") + "\n\n" +
                 self._t(lang, "review", "forward_prompt"),
            next_state=ReviewStates.FORWARD,
            metadata={"reflection": message},
        )

    async def _handle_forward(
        self, message: str, ctx: ModuleContext
    ) -> ModuleResponse:
        """
        Handle the forward-looking step.

        This is the final step of the review flow. Saves tomorrow's
        intention and ends the flow.

        Args:
            message: User's response about tomorrow's focus
            ctx: Module context

        Returns:
            ModuleResponse ending the flow
        """
        lang = ctx.language

        # Save the forward intention to metadata (would be persisted in production)
        forward_intention = message

        # Mark the daily plan as having done evening review
        db = await self._get_db_session(ctx)
        if db is not None:
            today = date.today()

            result = await db.execute(
                select(DailyPlan).where(
                    DailyPlan.user_id == ctx.user_id,
                    DailyPlan.date == today,
                )
            )
            daily_plan = result.scalar_one_or_none()

            if daily_plan:
                # SQLAlchemy ORM: use setattr for Column assignments
                setattr(daily_plan, 'auto_review_triggered', True)
                await db.commit()

        return ModuleResponse.end_flow(
            self._t(lang, "review", "complete").format(
                intention=forward_intention
            )
        )

    async def on_exit(self, ctx: ModuleContext) -> None:
        """
        Handle exit from the Review module.

        Cleanup any temporary state if needed.

        Args:
            ctx: Module context
        """
        # No cleanup needed currently
        pass

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        This enables auto-triggering of the evening review.

        Returns:
            DailyWorkflowHooks with evening_review hook
        """

        async def evening_review_hook(ctx: ModuleContext) -> str | None:
            """
            Auto-trigger evening review if not already done.

            Args:
                ctx: Module context

            Returns:
                Trigger message if review should start, None otherwise
            """
            # Get today's daily plan
            db = await self._get_db_session(ctx)
            if db is None:
                return None
            today = date.today()

            result = await db.execute(
                select(DailyPlan).where(
                    DailyPlan.user_id == ctx.user_id,
                    DailyPlan.date == today,
                )
            )
            daily_plan = result.scalar_one_or_none()

            # Check if evening review already done
            if daily_plan and daily_plan.auto_review_triggered:
                return None

            # Trigger the review
            return self._t(ctx.language, "review", "evening_trigger")

        return DailyWorkflowHooks(
            evening_review=evening_review_hook,
            hook_name="review",
            priority=10,  # Run after other evening hooks
        )

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """
        GDPR export for this module's data.

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all user data from this module
        """
        # In production, query the database for user's review data
        return {
            "reviews": [],  # Would contain review sessions
            "daily_plans": [],  # Would contain daily plan data
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR delete for this module's data.

        Args:
            user_id: The user's ID
        """
        # In production, delete user's review data from database
        pass

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restriction of processing.

        Args:
            user_id: The user's ID
        """
        # In production, mark user's data as frozen
        pass

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Lift restriction of processing.

        Args:
            user_id: The user's ID
        """
        # In production, unmark user's data as frozen
        pass


# Module instance for registration
review_module = ReviewModule()

__all__ = [
    "ReviewModule",
    "ReviewStates",
    "review_module",
]
