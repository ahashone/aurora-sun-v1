"""
Future Letter Module for Aurora Sun V1.

This module guides users through a deep-dive future letter writing exercise:
1. SETTING: Set the letter (to yourself in 5/10/20 years)
2. LIFE_NOW: Describe your life right now
3. LOOKING_BACK: Looking back from the future, what do you see?
4. CHALLENGES: What challenges did you overcome?
5. WISDOM: What wisdom would you share?

The output feeds into vision anchoring for the Vision-to-Task pillar.

Reference:
- ARCHITECTURE.md Section 2 (Module System)
- ROADMAP.md: Vision-to-Task Pillar
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.core.segment_context import SegmentContext, WorkingStyleCode

if TYPE_CHECKING:
    from src.core.module_response import ModuleResponse


# =============================================================================
# Future Letter States
# =============================================================================

class FutureLetterState:
    """State machine states for the Future Letter Module."""

    # Initial state - set the letter (to yourself in X years)
    SETTING = "SETTING"

    # Describe your life right now
    LIFE_NOW = "LIFE_NOW"

    # Looking back from the future, what do you see?
    LOOKING_BACK = "LOOKING_BACK"

    # What challenges did you overcome?
    CHALLENGES = "CHALLENGES"

    # What wisdom would you share?
    WISDOM = "WISDOM"

    # Flow complete
    DONE = "DONE"

    # All states as a list for validation
    ALL = [
        SETTING,
        LIFE_NOW,
        LOOKING_BACK,
        CHALLENGES,
        WISDOM,
        DONE,
    ]


# =============================================================================
# Segment-specific prompts
# =============================================================================

SEGMENT_PROMPTS: dict[WorkingStyleCode, dict[str, str]] = {
    "AD": {
        "setting": "Let's imagine your future self! How far ahead do you want to write to yourself? 5, 10, or 20 years? Pick what feels exciting.",
        "life_now": "Paint a picture of your life right now. What's the reality? What's the chaos? What's the energy like?",
        "looking_back": "From that future vantage point, what do you see when you look back at this time?",
        "challenges": "What challenges did your future self overcome? What patterns broke? What felt impossible that became possible?",
        "wisdom": "If your future self could whisper one thing to present you, what would it be?",
    },
    "AU": {
        "setting": "Let's write a letter to your future self. How many years ahead feels right? 5, 10, or 20? Take your time deciding.",
        "life_now": "Describe your current life as you see it. What routines sustain you? What environments matter?",
        "looking_back": "From the future, looking back at today - what stands out? What was the foundation?",
        "challenges": "What challenges did you navigate? What strategies emerged? What helped you thrive?",
        "wisdom": "Your future self has perspective. What wisdom would they want to share with you now?",
    },
    "AH": {
        "setting": "Time to connect with your future self. How far ahead do you want to reach? 5, 10, or 20 years?",
        "life_now": "Describe your life right now - the good, the hard, the real. Include both the attention and sensory pieces.",
        "looking_back": "From that future perspective, what do you see when you look back at this chapter?",
        "challenges": "What challenges did you overcome? Consider both the attention stuff and the sensory/overload stuff - how did you navigate?",
        "wisdom": "Your future self knows both sides of your experience. What would they want you to know?",
    },
    "NT": {
        "setting": "Let's write a letter to your future self. How many years ahead would you like to write to? 5, 10, or 20?",
        "life_now": "Describe your current life. What's working? What's challenging? Where are you headed?",
        "looking_back": "From the future, looking back at today - what do you see? What's the bigger picture?",
        "challenges": "What challenges did you overcome on your journey? What did you learn about yourself?",
        "wisdom": "Your future self has wisdom to share. What would they want you to know?",
    },
    "CU": {
        "setting": "Let's write a letter to your future self. How many years ahead?",
        "life_now": "Describe your life right now.",
        "looking_back": "From the future, what do you see when you look back?",
        "challenges": "What challenges did you overcome?",
        "wisdom": "What wisdom would your future self share?",
    },
}


# =============================================================================
# Future Letter Session Data
# =============================================================================

@dataclass
class FutureLetterSession:
    """Session data for the future letter flow."""

    # Time horizon: 5, 10, or 20 years
    time_horizon: int | None = None

    # User's description of their life now
    life_now: str = ""

    # User's response to "looking back"
    looking_back: str = ""

    # Challenges overcome
    challenges: str = ""

    # Wisdom to share
    wisdom: str = ""

    # Final compiled letter
    compiled_letter: str | None = None

    # Timestamp
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# Future Letter Module
# =============================================================================

class FutureLetterModule:
    """
    Future Letter Module for Aurora Sun V1.

    This module guides users through a deep-dive future letter writing exercise
    that feeds into vision anchoring for the Vision-to-Task pillar.

    Key features:
    - Deep dive flow: setting → life_now → looking_back → challenges → wisdom
    - Feeds into vision anchoring (stored as vision data)
    - Natural language entry
    - Segment-specific prompts

    The output can be used to:
    - Anchor long-term vision in daily planning
    - Identify core values and motivations
    - Track personal growth over time
    """

    name: str = "future_letter"
    intents: list[str] = [
        "future_letter.start",
        "future_letter.write",
        "future_letter.continue",
    ]
    pillar: str = "vision_to_task"

    # State machine states (for reference)
    STATES = {
        "SETTING": "Set the letter (to yourself in 5/10/20 years)",
        "LIFE_NOW": "Describe your life right now",
        "LOOKING_BACK": "Looking back from the future, what do you see?",
        "CHALLENGES": "What challenges did you overcome?",
        "WISDOM": "What wisdom would you share?",
        "DONE": "Flow complete",
    }

    def __init__(self, db_session: Any = None):
        """
        Initialize the Future Letter Module.

        Args:
            db_session: Database session for letter persistence (optional, lazy loaded)
        """
        self._db_session = db_session
        self._session_data: dict[int, FutureLetterSession] = {}

    # =========================================================================
    # Module Protocol Implementation
    # =========================================================================

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Start a new future letter session.

        This is called when user enters the future_letter module.
        Prompts the user to set the time horizon for the letter.

        Args:
            ctx: Module context

        Returns:
            ModuleResponse with welcome message and initial prompt
        """
        # Initialize session data
        user_id = ctx.user_id
        if user_id not in self._session_data:
            self._session_data[user_id] = FutureLetterSession()

        session = self._session_data[user_id]

        # Get segment-specific prompt
        prompt = self._get_segment_prompt(ctx.segment_context, "setting")

        welcome_text = self._build_welcome_message(ctx)

        return ModuleResponse(
            text=f"{welcome_text}\n\n{prompt}",
            next_state=FutureLetterState.SETTING,
            metadata={
                "time_horizon_options": [5, 10, 20],
                "time_horizon": session.time_horizon,
            },
        )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle user message.

        Routes based on current based on current state state in the future letter flow:
        - SETTING: User selects time horizon (5/10/20 years)
        - LIFE_NOW: User describes their current life
        - LOOKING_BACK: User reflects from future perspective
        - CHALLENGES: User shares challenges overcome
        - WISDOM: User shares wisdom

        Args:
            message: User's input message
            ctx: Module context

        Returns:
            ModuleResponse with text, buttons, and state transitions
        """
        session = self._session_data.get(ctx.user_id)
        if session is None:
            # Restart session if not found
            return await self.on_enter(ctx)

        # Route to appropriate state handler
        state_handlers = {
            FutureLetterState.SETTING: self._handle_setting,
            FutureLetterState.LIFE_NOW: self._handle_life_now,
            FutureLetterState.LOOKING_BACK: self._handle_looking_back,
            FutureLetterState.CHALLENGES: self._handle_challenges,
            FutureLetterState.WISDOM: self._handle_wisdom,
        }

        handler = state_handlers.get(ctx.state)
        if handler:
            return await handler(message, ctx, session)
        else:
            # Unknown state, restart
            return await self.on_enter(ctx)

    async def on_exit(self, ctx: ModuleContext) -> None:
        """
        Clean up when leaving the future letter module.

        Persists the letter to database if complete.

        Args:
            ctx: Module context
        """
        user_id = ctx.user_id
        if user_id in self._session_data:
            # Persist letter if complete
            session = self._session_data[user_id]
            if session.compiled_letter:
                await self._persist_letter(ctx, session)

            # Clean up session
            del self._session_data[user_id]

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        Currently no automatic hooks - this is primarily a user-initiated module.

        Returns:
            DailyWorkflowHooks (empty for this module)
        """
        return DailyWorkflowHooks(
            hook_name="future_letter",
            priority=50,  # Lower priority - primarily manual trigger
        )

    # =========================================================================
    # GDPR Methods
    # =========================================================================

    async def export_user_data(self, user_id: int) -> dict:
        """
        GDPR export for future letter data.

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all future letter data
        """
        # TODO: Load from database when implemented
        return {
            "future_letters": [],
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR delete for future letter data.

        Args:
            user_id: The user's ID
        """
        # TODO: Implement actual deletion from database
        pass

    # =========================================================================
    # State Handlers
    # =========================================================================

    async def _handle_setting(
        self,
        message: str,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> ModuleResponse:
        """
        Handle SETTING state - user selects time horizon.

        Args:
            message: User's response (5, 10, or 20)
            ctx: Module context
            session: Future letter session data

        Returns:
            ModuleResponse
        """
        # Parse time horizon
        time_horizon = self._parse_time_horizon(message)

        if time_horizon is None:
            # Invalid response - ask again
            return ModuleResponse(
                text="I didn't catch that. How far ahead would you like to write to yourself? Choose 5, 10, or 20 years.",
                next_state=FutureLetterState.SETTING,
            )

        session.time_horizon = time_horizon

        # Get segment-specific prompt for life_now
        prompt = self._get_segment_prompt(ctx.segment_context, "life_now")

        return ModuleResponse(
            text=f"Perfect! Let's write to {time_horizon} years from now.\n\n{prompt}",
            next_state=FutureLetterState.LIFE_NOW,
            metadata={"time_horizon": time_horizon},
        )

    async def _handle_life_now(
        self,
        message: str,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> ModuleResponse:
        """
        Handle LIFE_NOW state - user describes current life.

        Args:
            message: User's description
            ctx: Module context
            session: Future letter session data

        Returns:
            ModuleResponse
        """
        session.life_now = message

        # Get segment-specific prompt for looking_back
        prompt = self._get_segment_prompt(ctx.segment_context, "looking_back")

        years = session.time_horizon or 10
        return ModuleResponse(
            text=f"Thank you for sharing that.\n\n{prompt}",
            next_state=FutureLetterState.LOOKING_BACK,
            metadata={"years": years},
        )

    async def _handle_looking_back(
        self,
        message: str,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> ModuleResponse:
        """
        Handle LOOKING_BACK state - user reflects from future perspective.

        Args:
            message: User's reflection
            ctx: Module context
            session: Future letter session data

        Returns:
            ModuleResponse
        """
        session.looking_back = message

        # Get segment-specific prompt for challenges
        prompt = self._get_segment_prompt(ctx.segment_context, "challenges")

        return ModuleResponse(
            text=f"Beautiful perspective.\n\n{prompt}",
            next_state=FutureLetterState.CHALLENGES,
        )

    async def _handle_challenges(
        self,
        message: str,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> ModuleResponse:
        """
        Handle CHALLENGES state - user shares challenges overcome.

        Args:
            message: User's response
            ctx: Module context
            session: Future letter session data

        Returns:
            ModuleResponse
        """
        session.challenges = message

        # Get segment-specific prompt for wisdom
        prompt = self._get_segment_prompt(ctx.segment_context, "wisdom")

        return ModuleResponse(
            text=f"That's powerful.\n\n{prompt}",
            next_state=FutureLetterState.WISDOM,
        )

    async def _handle_wisdom(
        self,
        message: str,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> ModuleResponse:
        """
        Handle WISDOM state - user shares wisdom to share.

        Compiles the letter and ends the flow.

        Args:
            message: User's wisdom
            ctx: Module context
            session: Future letter session data

        Returns:
            ModuleResponse
        """
        session.wisdom = message

        # Compile the letter
        session.compiled_letter = self._compile_letter(session)

        # Build completion message
        completion_text = self._build_completion_message(ctx, session)

        return ModuleResponse(
            text=completion_text,
            is_end_of_flow=True,
            side_effects=[
                {
                    "effect_type": "vision_anchor",
                    "payload": {
                        "letter": session.compiled_letter,
                        "time_horizon": session.time_horizon,
                        "key_insights": self._extract_key_insights(session),
                        "created_at": session.created_at.isoformat(),
                    },
                }
            ],
            metadata={
                "time_horizon": session.time_horizon,
                "letter_length": len(session.compiled_letter),
            },
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_segment_prompt(
        self,
        segment: SegmentContext,
        stage: str,
    ) -> str:
        """
        Get segment-specific prompt for the given stage.

        Args:
            segment: User's segment context
            stage: The current stage (setting, life_now, etc.)

        Returns:
            Localized or segment-specific prompt
        """
        # Get working style code
        code = segment.core.code

        # Fallback to CU if not found
        prompts = SEGMENT_PROMPTS.get(code, SEGMENT_PROMPTS["CU"])

        return prompts.get(stage, SEGMENT_PROMPTS["CU"].get(stage, ""))

    def _parse_time_horizon(self, message: str) -> int | None:
        """
        Parse time horizon from user message.

        Args:
            message: User's response

        Returns:
            5, 10, 20 or None
        """
        message_lower = message.lower().strip()

        # Check for explicit numbers first
        if "5" in message_lower and "20" not in message_lower:
            return 5
        if "10" in message_lower:
            return 10
        if "20" in message_lower:
            return 20

        # Check for words
        if "five" in message_lower:
            return 5
        if "ten" in message_lower:
            return 10
        if "twenty" in message_lower:
            return 20

        return None

    def _compile_letter(self, session: FutureLetterSession) -> str:
        """
        Compile the complete future letter from session data.

        Args:
            session: Future letter session data

        Returns:
            Compiled letter text
        """
        years = session.time_horizon or 10

        letter = f"""Dear Future Me,

Writing to you from {years} years ago...

**My Life Right Now:**
{session.life_now}

**Looking Back:**
{session.looking_back}

**Challenges Overcome:**
{session.challenges}

**Wisdom to Share:**
{session.wisdom}

---
Written on {session.created_at.strftime('%Y-%m-%d')}
"""

        return letter

    def _extract_key_insights(self, session: FutureLetterSession) -> list[str]:
        """
        Extract key insights from the letter for vision anchoring.

        Args:
            session: Future letter session data

        Returns:
            List of key insights
        """
        insights = []

        # Extract first sentence from each section as a summary
        if session.life_now:
            first_line = session.life_now.split(".")[0].strip()
            if first_line:
                insights.append(f"Current life: {first_line}")

        if session.challenges:
            first_line = session.challenges.split(".")[0].strip()
            if first_line:
                insights.append(f"Challenges: {first_line}")

        if session.wisdom:
            first_line = session.wisdom.split(".")[0].strip()
            if first_line:
                insights.append(f" Wisdom: {first_line}")

        return insights

    def _build_welcome_message(self, ctx: ModuleContext) -> str:
        """
        Build the welcome message.

        Args:
            ctx: Module context

        Returns:
            Welcome message text
        """

        user_name = ctx.metadata.get("user_name", "there")
        return (
            f"Welcome to the Future Letter exercise, {user_name}!\n\n"
            f"This is a powerful exercise for vision anchoring. "
            f"You'll write a letter to your future self, exploring where you are now, "
            f"where you're heading, and what wisdom you'd share."
        )

    def _build_completion_message(
        self,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> str:
        """
        Build the completion message with the compiled letter.

        Args:
            ctx: Module context
            session: Future letter session data

        Returns:
            Completion message text
        """

        return (
            "Beautiful! You've written a powerful letter to your future self.\n\n"
            "I've saved this for you. This letter can serve as an anchor for your vision "
            "and daily planning. When you're setting your priorities, you can look back "
            "at what your future self wanted you to know.\n\n"
            "Here's your letter:\n\n"
            "---"
        )

    async def _persist_letter(
        self,
        ctx: ModuleContext,
        session: FutureLetterSession,
    ) -> None:
        """
        Persist the letter to database.

        Args:
            ctx: Module context
            session: Future letter session with compiled letter
        """
        # TODO: Implement actual persistence to Vision model
        # The letter can feed into the vision anchoring system
        pass


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "FutureLetterModule",
    "FutureLetterState",
    "FutureLetterSession",
]
