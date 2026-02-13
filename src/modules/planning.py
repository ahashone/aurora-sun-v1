"""
Planning Module for Aurora Sun V1.

This module handles the daily planning workflow, guiding users through:
1. Vision alignment check (90d goals)
2. Overview of pending tasks from previous sessions
3. Priority selection (segment-specific limits)
4. Task breakdown
5. Segment constraint validation
6. Today's commitment

Reference:
- ARCHITECTURE.md Section 2 (Module System)
- ARCHITECTURE.md Section 14 (Planning Module)
- ROADMAP.md 1.2: Planning Module
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Any, TYPE_CHECKING

from src.core.module_protocol import Module
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.segment_context import SegmentContext

if TYPE_CHECKING:
    from src.models.task import Task
    from src.models.goal import Goal
    from src.models.vision import Vision


# =============================================================================
# Planning Module States
# =============================================================================

class PlanningState:
    """State machine states for the Planning Module."""

    # Initial state - ask what user wants to accomplish
    SCOPE = "SCOPE"

    # Display vision + 90d goals BEFORE task list
    VISION = "VISION"

    # Show existing tasks and pending items
    OVERVIEW = "OVERVIEW"

    # Select priorities (max based on segment)
    PRIORITIES = "PRIORITIES"

    # Break down priorities into tasks
    BREAKDOWN = "BREAKDOWN"

    # Validate against segment constraints
    SEGMENT_CHECK = "SEGMENT_CHECK"

    # Confirm today's commitment
    COMMITMENT = "COMMITMENT"

    # Flow complete
    DONE = "DONE"

    # All states as a list for validation
    ALL = [
        SCOPE,
        VISION,
        OVERVIEW,
        PRIORITIES,
        BREAKDOWN,
        SEGMENT_CHECK,
        COMMITMENT,
        DONE,
    ]


# =============================================================================
# Planning Data Structures
# =============================================================================

@dataclass
class PriorityItem:
    """A priority item selected by the user."""

    id: str
    title: str
    goal_id: Optional[int] = None
    estimated_minutes: Optional[int] = None


@dataclass
class PlanningSession:
    """Session data for the planning flow."""

    # What user wants to accomplish
    scope: str = ""

    # Selected priorities (max based on segment)
    priorities: list[PriorityItem] = field(default_factory=list)

    # Tasks derived from priorities
    tasks: list[dict[str, Any]] = field(default_factory=list)

    # 90d goals for vision alignment
    goals_90d: list[dict[str, Any]] = field(default_factory=list)

    # User's vision
    vision_content: Optional[str] = None

    # User confirmed vision alignment
    vision_aligned: bool = False


# =============================================================================
# Planning Module
# =============================================================================

class PlanningModule:
    """
    Planning Module for Aurora Sun V1.

    Implements the daily planning workflow with segment-specific behavior:
    - ADHD: max 2 priorities, 25 min sprints, cumulative gamification, NO streaks
    - Autism: max 3, 45 min, sensory check, routine anchoring
    - AuDHD: max 3, 35 min, channel check, ICNU, integrity trigger
    - Neurotypical: max 3, 40 min, standard

    Key features:
    - Vision alignment check: "Does today's plan serve your vision?"
    - Task persistence: Load pending tasks from previous sessions
    - Segment-specific constraint validation
    """

    name: str = "planning"
    intents: list[str] = [
        "planning.start",
        "planning.prioritize",
        "planning.breakdown",
        "planning.add_task",
        "planning.show_tasks",
    ]
    pillar: str = "vision_to_task"

    # State machine states (for reference)
    STATES = {
        "SCOPE": "Ask what user wants to accomplish",
        "VISION": "Display vision + 90d goals BEFORE task list",
        "OVERVIEW": "Show existing tasks and pending items",
        "PRIORITIES": "Select priorities (max based on segment)",
        "BREAKDOWN": "Break down priorities into tasks",
        "SEGMENT_CHECK": "Validate against segment constraints",
        "COMMITMENT": "Confirm today's commitment",
        "DONE": "Flow complete",
    }

    def __init__(self, db_session: Any = None):
        """
        Initialize the Planning Module.

        Args:
            db_session: Database session for task persistence (optional, lazy loaded)
        """
        self._db_session = db_session
        # F-008: Use bounded state store instead of unbounded dict
        from src.services.state_store import get_state_store
        self._state_store = get_state_store()
        self._session_key_prefix = "planning:session:"

    # =========================================================================
    # Module Protocol Implementation
    # =========================================================================

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """
        Start a fresh planning session.

        This is called when user enters the planning module.
        Displays user's vision + 90d goals FIRST, then shows pending tasks.

        Args:
            ctx: Module context

        Returns:
            ModuleResponse with welcome message and initial prompt
        """
        # F-008: Use bounded state store with TTL
        user_id = ctx.user_id
        session_key = f"{self._session_key_prefix}{user_id}"
        session = self._state_store.get(session_key)

        if session is None:
            session = PlanningSession()
            # Store with 1 hour TTL
            self._state_store.set(session_key, session, ttl=3600)

        # Load user's vision and 90d goals
        await self._load_vision_and_goals(ctx, session)

        # Load user's vision and 90d goals
        await self._load_vision_and_goals(ctx, session)

        # Get segment-specific configuration
        segment = ctx.segment_context
        max_priorities = segment.core.max_priorities
        sprint_minutes = segment.core.sprint_minutes

        # Build welcome message with segment-specific framing
        welcome_text = self._build_welcome_message(
            ctx=ctx,
            session=session,
            max_priorities=max_priorities,
            sprint_minutes=sprint_minutes,
        )

        # Transition to VISION state (show vision first)
        return ModuleResponse(
            text=welcome_text,
            next_state=PlanningState.VISION,
            metadata={
                "max_priorities": max_priorities,
                "sprint_minutes": sprint_minutes,
                "has_vision": session.vision_content is not None,
                "has_goals": len(session.goals_90d) > 0,
                "has_pending_tasks": False,  # Will be populated in OVERVIEW
            },
        )

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """
        Handle user message based on current state.

        Routes based on current state in the planning flow:
        - VISION: "Does today's plan serve your vision?"
        - OVERVIEW: Show pending tasks, get scope
        - PRIORITIES: Enforce max_priorities from SegmentContext
        - BREAKDOWN: Break down priorities into tasks
        - SEGMENT_CHECK: Validate against segment constraints
        - COMMITMENT: Confirm and persist today's commitment

        Args:
            message: User's input message
            ctx: Module context

        Returns:
            ModuleResponse with text, buttons, and state transitions
        """
        # F-008: Use bounded state store with TTL
        session_key = f"{self._session_key_prefix}{ctx.user_id}"
        session = self._state_store.get(session_key)
        if session is None:
            # Restart session if not found
            return await self.on_enter(ctx)

        # Route to appropriate state handler
        state_handlers = {
            PlanningState.SCOPE: self._handle_scope,
            PlanningState.VISION: self._handle_vision,
            PlanningState.OVERVIEW: self._handle_overview,
            PlanningState.PRIORITIES: self._handle_priorities,
            PlanningState.BREAKDOWN: self._handle_breakdown,
            PlanningState.SEGMENT_CHECK: self._handle_segment_check,
            PlanningState.COMMITMENT: self._handle_commitment,
        }

        handler = state_handlers.get(ctx.state)
        if handler:
            return await handler(message, ctx, session)
        else:
            # Unknown state, restart
            return await self.on_enter(ctx)

    async def on_exit(self, ctx: ModuleContext) -> None:
        """
        Clean up when leaving the planning module.

        Args:
            ctx: Module context
        """
        # F-008: Use bounded state store with TTL
        session_key = f"{self._session_key_prefix}{ctx.user_id}"
        session = self._state_store.get(session_key)
        if session:
            # Optionally persist session data before cleanup
            await self._persist_session(ctx, session)
            # Delete from state store
            self._state_store.delete(session_key)

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """
        Return hooks for the daily workflow.

        planning_enrichment: Surface pending tasks from previous sessions

        Returns:
            DailyWorkflowHooks with planning_enrichment hook
        """
        return DailyWorkflowHooks(
            planning_enrichment=self._planning_enrichment_hook,
            hook_name="planning",
            priority=10,  # Run early
        )

    # =========================================================================
    # GDPR Methods
    # =========================================================================

    async def export_user_data(self, user_id: int) -> dict:
        """
        GDPR export for planning data.

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all planning-related data
        """
        # TODO: Load from database when implemented
        return {
            "tasks": [],
            "goals": [],
            "visions": [],
            "planning_sessions": [],
        }

    async def delete_user_data(self, user_id: int) -> None:
        """
        GDPR delete for planning data.

        Args:
            user_id: The user's ID
        """
        # TODO: Implement actual deletion from database
        pass

    async def freeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Restrict processing.

        Args:
            user_id: The user's ID
        """
        # TODO: Mark user data as restricted
        pass

    async def unfreeze_user_data(self, user_id: int) -> None:
        """
        GDPR Art. 18: Lift restriction.

        Args:
            user_id: The user's ID
        """
        # TODO: Remove restriction flag
        pass

    # =========================================================================
    # State Handlers
    # =========================================================================

    async def _handle_scope(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle SCOPE state - ask what user wants to accomplish.

        Args:
            message: User's message
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        session.scope = message

        # Move to VISION state
        return ModuleResponse(
            text=self._get_message(ctx, "scope_acknowledged"),
            next_state=PlanningState.VISION,
        )

    async def _handle_vision(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle VISION state - vision alignment check.

        Key question: "Does today's plan serve your vision?"

        Args:
            message: User's response
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        # F-013: Use word boundary matching instead of substring
        import re
        message_lower = message.lower().strip()

        # Strict yes/no patterns (word boundary matching)
        yes_pattern = re.compile(r'\b(yes|y|ja|si|da|yeah|yep|sure|ok|okay)\b')
        no_pattern = re.compile(r'\b(no|n|nein|nao|nope|not really)\b')

        if yes_pattern.search(message_lower):
            session.vision_aligned = True

            # Show pending tasks from previous sessions
            pending_tasks = await self._load_pending_tasks(ctx)

            if pending_tasks:
                # Show overview with pending tasks
                return ModuleResponse(
                    text=self._build_overview_message(ctx, session, pending_tasks),
                    next_state=PlanningState.OVERVIEW,
                    metadata={"pending_tasks_count": len(pending_tasks)},
                )
            else:
                # Skip to priorities if no pending tasks
                return ModuleResponse(
                    text=self._get_message(ctx, "no_pending_tasks"),
                    next_state=PlanningState.PRIORITIES,
                )

        elif no_pattern.search(message_lower):
            # User says no - help them realign
            return ModuleResponse(
                text=self._get_message(ctx, "realign_with_vision"),
                next_state=PlanningState.VISION,  # Stay in VISION
            )

        else:
            # Ambiguous response - ask again
            return ModuleResponse(
                text=self._get_message(ctx, "vision_check_clarify"),
                next_state=PlanningState.VISION,
            )

    async def _handle_overview(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle OVERVIEW state - show pending tasks and get scope.

        Args:
            message: User's response
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        # Store user's scope if provided
        if message.strip():
            session.scope = message

        # Move to PRIORITIES
        max_priorities = ctx.segment_context.core.max_priorities

        return ModuleResponse(
            text=self._build_priorities_prompt(ctx, max_priorities),
            next_state=PlanningState.PRIORITIES,
        )

    async def _handle_priorities(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle PRIORITIES state - select priorities.

        Enforces max_priorities from SegmentContext:
        - ADHD: max 2
        - Autism: max 3
        - AuDHD: max 3
        - Neurotypical: max 3

        Args:
            message: User's priorities
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        segment = ctx.segment_context
        max_priorities = segment.core.max_priorities

        # Parse priorities from message
        priorities = self._parse_priorities(message, max_priorities)

        if len(priorities) > max_priorities:
            # Too many priorities - ask to reduce
            return ModuleResponse(
                text=self._get_message(ctx, "too_many_priorities").format(
                    max=max_priorities,
                    count=len(priorities),
                ),
                next_state=PlanningState.PRIORITIES,
            )

        session.priorities = priorities

        # Check if segment check is needed
        if segment.features.sensory_check_required:
            # AU/AH: need sensory check before breakdown
            return ModuleResponse(
                text=self._get_message(ctx, "sensory_check"),
                next_state=PlanningState.SEGMENT_CHECK,
                metadata={"sensory_check_required": True},
            )
        elif segment.features.icnu_enabled:
            # AD/AH: ICNU check
            return ModuleResponse(
                text=self._get_message(ctx, "icnu_check"),
                next_state=PlanningState.SEGMENT_CHECK,
                metadata={"icnu_check_required": True},
            )
        elif segment.features.channel_dominance_enabled:
            # AH: channel dominance check
            return ModuleResponse(
                text=self._get_message(ctx, "channel_check"),
                next_state=PlanningState.SEGMENT_CHECK,
                metadata={"channel_check_required": True},
            )
        else:
            # NT: skip to breakdown
            return ModuleResponse(
                text=self._get_message(ctx, "priorities_accepted").format(
                    count=len(priorities),
                ),
                next_state=PlanningState.BREAKDOWN,
            )

    async def _handle_breakdown(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle BREAKDOWN state - break down priorities into tasks.

        Args:
            message: User's task breakdown
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        # Parse tasks from message
        tasks = self._parse_tasks(message, session.priorities)
        session.tasks = tasks

        # Move to commitment
        sprint_minutes = ctx.segment_context.core.sprint_minutes

        return ModuleResponse(
            text=self._build_commitment_message(ctx, session, sprint_minutes),
            next_state=PlanningState.COMMITMENT,
        )

    async def _handle_segment_check(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle SEGMENT_CHECK state - validate segment-specific constraints.

        Handles:
        - Sensory check (AU/AH)
        - ICNU check (AD/AH)
        - Channel dominance check (AH)
        - Integrity trigger (AH)

        Args:
            message: User's response to segment check
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        metadata = ctx.metadata or {}

        # Process based on check type
        if metadata.get("sensory_check_required"):
            # Check sensory state
            if self._is_sensory_overloaded(message):
                return ModuleResponse(
                    text=self._get_message(ctx, "sensory_overload_redirect"),
                    is_end_of_flow=True,
                )

        if metadata.get("icnu_check_required"):
            # Check ICNU charge
            icnu_charge = self._parse_icnu(message)
            if icnu_charge < 3:
                return ModuleResponse(
                    text=self._get_message(ctx, "low_icnu_adjust"),
                    next_state=PlanningState.PRIORITIES,
                )

        if metadata.get("channel_check_required"):
            # Check channel dominance
            channel = self._parse_channel(message)
            if not channel:
                return ModuleResponse(
                    text=self._get_message(ctx, "channel_check_clarify"),
                    next_state=PlanningState.SEGMENT_CHECK,
                )

        if metadata.get("integrity_trigger_enabled"):
            # Check integrity alignment
            if not self._check_integrity(message, session):
                return ModuleResponse(
                    text=self._get_message(ctx, "integrity_mismatch"),
                    next_state=PlanningState.PRIORITIES,
                )

        # All checks passed
        return ModuleResponse(
            text=self._get_message(ctx, "segment_check_passed"),
            next_state=PlanningState.BREAKDOWN,
        )

    async def _handle_commitment(
        self,
        message: str,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> ModuleResponse:
        """
        Handle COMMITMENT state - confirm and persist today's commitment.

        Args:
            message: User's confirmation
            ctx: Module context
            session: Planning session data

        Returns:
            ModuleResponse
        """
        # F-013: Use word boundary matching instead of substring
        import re
        message_lower = message.lower().strip()

        # Strict confirmation patterns (word boundary matching)
        yes_pattern = re.compile(r'\b(yes|y|ja|si|da|yep|sure|ok|okay|confirm|commit)\b')
        no_pattern = re.compile(r'\b(no|n|nein|nao|nope|change|modify|edit)\b')

        if yes_pattern.search(message_lower):
            # Persist tasks
            await self._persist_tasks(ctx, session)

            # Build success message with segment-specific gamification
            segment = ctx.segment_context
            gamification = segment.ux.gamification

            return ModuleResponse(
                text=self._get_message(ctx, "commitment_confirmed"),
                is_end_of_flow=True,
                side_effects=[
                    {
                        "effect_type": "create_tasks",
                        "payload": {
                            "tasks": session.tasks,
                            "committed_date": date.today().isoformat(),
                        },
                    }
                ],
                metadata={
                    "gamification": gamification,
                    "tasks_created": len(session.tasks),
                },
            )

        elif no_pattern.search(message_lower):
            # User wants to modify - go back to breakdown
            return ModuleResponse(
                text=self._get_message(ctx, "commitment_modify"),
                next_state=PlanningState.BREAKDOWN,
            )

        else:
            # Clarify
            return ModuleResponse(
                text=self._get_message(ctx, "commitment_clarify"),
                next_state=PlanningState.COMMITMENT,
            )

    # =========================================================================
    # Daily Workflow Hooks
    # =========================================================================

    async def _planning_enrichment_hook(
        self,
        ctx: ModuleContext,
    ) -> Optional[str]:
        """
        Hook to surface pending tasks from previous sessions.

        Called during planning_enrichment phase of daily workflow.

        Args:
            ctx: Module context

        Returns:
            Message with pending tasks, or None if no pending tasks
        """
        pending_tasks = await self._load_pending_tasks(ctx)

        if not pending_tasks:
            return None

        # Build pending tasks message
        task_list = "\n".join(
            f"- {task.get('title', 'Untitled')}"
            for task in pending_tasks[:5]  # Limit to 5
        )

        return f"You have {len(pending_tasks)} pending task(s) from previous sessions:\n{task_list}"

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _load_vision_and_goals(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> None:
        """
        Load user's vision and 90d goals from database.

        Args:
            ctx: Module context
            session: Planning session to populate
        """
        # TODO: Load from database when implemented
        # For now, return placeholder data
        session.vision_content = None
        session.goals_90d = []

    async def _load_pending_tasks(self, ctx: ModuleContext) -> list[dict[str, Any]]:
        """
        Load pending tasks from previous sessions.

        Args:
            ctx: Module context

        Returns:
            List of pending task dicts
        """
        # TODO: Load from database when implemented
        # For now, return empty list
        return []

    async def _persist_tasks(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> None:
        """
        Persist tasks to database.

        Args:
            ctx: Module context
            session: Planning session with tasks
        """
        # TODO: Implement actual persistence to Task model
        pass

    async def _persist_session(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
    ) -> None:
        """
        Persist session data before cleanup.

        Args:
            ctx: Module context
            session: Planning session data
        """
        # TODO: Implement if needed for session recovery
        pass

    def _build_welcome_message(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
        max_priorities: int,
        sprint_minutes: int,
    ) -> str:
        """
        Build welcome message with segment-specific framing.

        Args:
            ctx: Module context
            session: Planning session
            max_priorities: Max priorities for this segment
            sprint_minutes: Sprint duration for this segment

        Returns:
            Welcome message text
        """
        segment = ctx.segment_context
        display_name = segment.core.display_name

        # Build vision section
        vision_section = ""
        if session.vision_content:
            vision_section = f"\n\nYour Vision:\n{session.vision_content[:200]}..."
        elif session.goals_90d:
            goals_text = "\n".join(
                f"- {goal.get('title', 'Untitled')}"
                for goal in session.goals_90d[:3]
            )
            vision_section = f"\n\nYour 90-Day Goals:\n{goals_text}"

        # Build segment-specific guidance
        guidance = self._get_segment_guidance(segment)

        return (
            f"Welcome to your daily planning, {ctx.language}!\n"
            f"{vision_section}\n\n"
            f"{guidance}\n\n"
            f"First, let me ask: **Does today's plan serve your vision?**\n"
            f"(Think about your 90-day goals as you answer)"
        )

    def _get_segment_guidance(self, segment: SegmentContext) -> str:
        """
        Get segment-specific guidance text.

        Uses SegmentContext fields, NOT segment code checks.

        Args:
            segment: User's segment context

        Returns:
            Guidance text
        """
        max_priorities = segment.core.max_priorities
        sprint_minutes = segment.core.sprint_minutes

        # Build guidance based on segment features
        features = segment.features

        if features.routine_anchoring:
            # Autism: routine anchoring
            return (
                f"For today, let's focus on {max_priorities} priority(ies). "
                f"We'll work in {sprint_minutes}-minute focused sessions with regular breaks. "
                f"This structure helps maintain consistency."
            )
        elif features.icnu_enabled and features.sensory_check_required:
            # AuDHD: both ICNU and sensory
            return (
                f"Let's plan together. We'll aim for {max_priorities} priorities "
                f"with {sprint_minutes}-minute work blocks. "
                f"I'll check in on your energy and sensory state to keep things sustainable."
            )
        elif features.icnu_enabled:
            # ADHD: ICNU-based
            return (
                f"Today we'll select up to {max_priorities} priorities. "
                f"We'll work in {sprint_minutes}-minute focused sprints. "
                f"I'll help you stay in your optimal activation zone."
            )
        else:
            # Neurotypical / default
            return (
                f"Let's plan your day. You can select up to {max_priorities} priorities, "
                f"working in {sprint_minutes}-minute focused blocks."
            )

    def _build_overview_message(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
        pending_tasks: list[dict[str, Any]],
    ) -> str:
        """
        Build overview message with pending tasks.

        Args:
            ctx: Module context
            session: Planning session
            pending_tasks: List of pending tasks

        Returns:
            Overview message
        """
        task_list = "\n".join(
            f"- {task.get('title', 'Untitled')}"
            for task in pending_tasks[:5]
        )

        more_count = len(pending_tasks) - 5
        more_text = f"\n(+{more_count} more)" if more_count > 0 else ""

        return (
            f"Here are your pending tasks from previous sessions:\n\n"
            f"{task_list}{more_text}\n\n"
            f"What would you like to focus on today? You can:\n"
            f"- Continue with pending tasks\n"
            f"- Start something new\n"
            f"- Mix of both"
        )

    def _build_priorities_prompt(
        self,
        ctx: ModuleContext,
        max_priorities: int,
    ) -> str:
        """
        Build priorities selection prompt.

        Args:
            ctx: Module context
            max_priorities: Maximum number of priorities

        Returns:
            Prompt text
        """
        return (
            f"Please select up to {max_priorities} priority(ies) for today.\n\n"
            f"What matters most? Tell me in your own words what you want to accomplish."
        )

    def _build_commitment_message(
        self,
        ctx: ModuleContext,
        session: PlanningSession,
        sprint_minutes: int,
    ) -> str:
        """
        Build commitment confirmation message.

        Args:
            ctx: Module context
            session: Planning session
            sprint_minutes: Sprint duration

        Returns:
            Commitment message
        """
        task_list = "\n".join(
            f"- {task.get('title', 'Untitled')}"
            for task in session.tasks[:3]
        )

        more_count = len(session.tasks) - 3
        more_text = f"\n(+{more_count} more)" if more_count > 0 else ""

        return (
            f"Here's your plan for today:\n\n"
            f"{task_list}{more_text}\n\n"
            f"We'll work in {sprint_minutes}-minute focused sessions.\n\n"
            f"Do you commit to this plan? (Yes/No or modify)"
        )

    def _parse_priorities(
        self,
        message: str,
        max_priorities: int,
    ) -> list[PriorityItem]:
        """
        Parse priorities from user message.

        Args:
            message: User's message
            max_priorities: Maximum allowed

        Returns:
            List of PriorityItem
        """
        # Simple parsing - split by newlines or numbered list
        lines = message.strip().split("\n")
        priorities = []

        for i, line in enumerate(lines[:max_priorities]):
            line = line.strip()
            # Remove numbering if present
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                line = line[1:].strip()

            if line:
                priorities.append(
                    PriorityItem(
                        id=f"priority_{i + 1}",
                        title=line,
                    )
                )

        return priorities

    def _parse_tasks(
        self,
        message: str,
        priorities: list[PriorityItem],
    ) -> list[dict[str, Any]]:
        """
        Parse tasks from user message.

        Args:
            message: User's message
            priorities: Parent priorities

        Returns:
            List of task dicts
        """
        # Simple parsing - each line is a task
        lines = message.strip().split("\n")
        tasks = []

        for i, line in enumerate(lines):
            line = line.strip()
            if line and len(line) > 2:
                # Remove numbering/bullets
                if line[0].isdigit() or line.startswith("-") or line.startswith("*"):
                    line = line[1:].strip()

                if line:
                    tasks.append({
                        "id": f"task_{i + 1}",
                        "title": line,
                        "priority": 1,  # Default priority
                    })

        return tasks

    def _is_sensory_overloaded(self, message: str) -> bool:
        """
        Check if user indicates sensory overload.

        Args:
            message: User's response

        Returns:
            True if overloaded
        """
        overloaded_indicators = [
            "overwhelmed", "too much", "sensory",
            "drained", "burned out", "can't handle",
            "overload", "shut down", "shutting down",
        ]
        message_lower = message.lower()
        return any(indicator in message_lower for indicator in overloaded_indicators)

    def _parse_icnu(self, message: str) -> int:
        """
        Parse ICNU charge from message.

        Args:
            message: User's response

        Returns:
            ICNU charge (1-5)
        """
        # Simple parsing - look for numbers
        import re

        numbers = re.findall(r'\d+', message)
        if numbers:
            charge = int(numbers[0])
            return max(1, min(5, charge))

        # Default to middle
        return 3

    def _parse_channel(self, message: str) -> Optional[str]:
        """
        Parse channel dominance from message.

        Args:
            message: User's response

        Returns:
            Channel name or None
        """
        channels = ["focus", "creative", "social", "physical", "learning"]
        message_lower = message.lower()

        for channel in channels:
            if channel in message_lower:
                return channel

        return None

    def _check_integrity(
        self,
        message: str,
        session: PlanningSession,
    ) -> bool:
        """
        Check if plan aligns with integrity values.

        Args:
            message: User's response
            session: Planning session

        Returns:
            True if aligned
        """
        # Simple check - user says it's aligned
        yes_responses = ["yes", "y", "aligned", "fits", "matches"]
        return any(yes in message.lower() for yes in yes_responses)

    # =========================================================================
    # i18n Helper
    # =========================================================================

    def _get_message(self, ctx: ModuleContext, key: str) -> str:
        """
        Get localized message for key.

        Args:
            ctx: Module context
            key: Message key

        Returns:
            Localized message
        """
        # TODO: Implement proper i18n
        # For now, return English messages

        messages = {
            "scope_acknowledged": "Got it. Let's make sure this serves your vision first.",
            "realign_with_vision": "Let's realign with your vision. What matters most right now?",
            "vision_check_clarify": "Please answer yes or no - does this plan serve your vision?",
            "no_pending_tasks": "No pending tasks from before. Let's focus on today's priorities.",
            "too_many_priorities": "I understand you want to do {count} things, but to stay focused, let's limit to {max}. Which are most important?",
            "sensory_check": "Before we break this down, how's your sensory state? Are you feeling calm or overwhelmed?",
            "icnu_check": "What's your energy level right now? (1=low, 5=high)",
            "channel_check": "Which channel feels most aligned right now? (focus, creative, social, physical, learning)",
            "channel_check_clarify": "Which channel fits best? focus, creative, social, physical, or learning?",
            "priorities_accepted": "Got {count} priority(ies). Let's break these into specific tasks.",
            "segment_check_passed": "Good. Now let's break this down into actionable tasks.",
            "sensory_overload_redirect": "It sounds like you're experiencing sensory overload. Let's take it easy today - maybe just one small task or rest.",
            "low_icnu_adjust": "Your energy is low. Let's adjust - perhaps fewer priorities or shorter sessions?",
            "integrity_mismatch": "This doesn't quite align with your values. Let's realign before committing.",
            "commitment_confirmed": "Your plan is set! You've got this. I'll check in later.",
            "commitment_modify": "No problem. What would you like to change?",
            "commitment_clarify": "Please confirm (yes) or let me know what to change.",
        }

        return messages.get(key, key)


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "PlanningModule",
    "PlanningState",
    "PlanningSession",
    "PriorityItem",
]
