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

from typing import TYPE_CHECKING, Any

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.gdpr_mixin import GDPRModuleMixin
from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse

# Import from sub-modules
from src.modules.planning_handlers import (
    handle_breakdown,
    handle_commitment,
    handle_overview,
    handle_priorities,
    handle_scope,
    handle_segment_check,
    handle_vision,
)
from src.modules.planning_helpers import (
    build_welcome_message,
    check_integrity as _check_integrity,
    get_segment_guidance as _get_segment_guidance,
    is_sensory_overloaded as _is_sensory_overloaded,
    parse_channel as _parse_channel,
    parse_icnu as _parse_icnu,
    parse_priorities as _parse_priorities,
    parse_tasks as _parse_tasks,
)
from src.modules.planning_state import (
    PlanningSession,
    PlanningState,
    PriorityItem,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Planning Module
# =============================================================================

class PlanningModule(GDPRModuleMixin):
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
        state_store = await self._state_store
        session = await state_store.get(session_key)

        if session is None:
            session = PlanningSession()
            # Store with 1 hour TTL
            await state_store.set(session_key, session, ttl=3600)

        # Load user's vision and 90d goals
        await self._load_vision_and_goals(ctx, session)

        # Get segment-specific configuration
        segment = ctx.segment_context
        max_priorities = segment.core.max_priorities
        sprint_minutes = segment.core.sprint_minutes

        # Build welcome message with segment-specific framing
        welcome_text = build_welcome_message(
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

        Routes based on current state in the planning flow.

        Args:
            message: User's input message
            ctx: Module context

        Returns:
            ModuleResponse with text, buttons, and state transitions
        """
        # F-008: Use bounded state store with TTL
        session_key = f"{self._session_key_prefix}{ctx.user_id}"
        state_store = await self._state_store
        session = await state_store.get(session_key)
        if session is None:
            # Restart session if not found
            return await self.on_enter(ctx)

        # Route to appropriate state handler
        if ctx.state == PlanningState.SCOPE:
            return await handle_scope(message, ctx, session)
        elif ctx.state == PlanningState.VISION:
            return await handle_vision(
                message, ctx, session, self._load_pending_tasks,
            )
        elif ctx.state == PlanningState.OVERVIEW:
            return await handle_overview(message, ctx, session)
        elif ctx.state == PlanningState.PRIORITIES:
            return await handle_priorities(message, ctx, session)
        elif ctx.state == PlanningState.BREAKDOWN:
            return await handle_breakdown(message, ctx, session)
        elif ctx.state == PlanningState.SEGMENT_CHECK:
            return await handle_segment_check(message, ctx, session)
        elif ctx.state == PlanningState.COMMITMENT:
            return await handle_commitment(
                message, ctx, session, self._persist_tasks,
            )
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
        state_store = await self._state_store
        session = await state_store.get(session_key)
        if session:
            # Optionally persist session data before cleanup
            await self._persist_session(ctx, session)
            # Delete from state store
            await state_store.delete(session_key)

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

    def _gdpr_data_categories(self) -> dict[str, list[str]]:
        """Declare planning data categories for GDPR."""
        return {
            "tasks": ["title", "priority", "committed_date"],
            "goals": ["title", "key_results"],
            "visions": ["content"],
            "planning_sessions": ["scope", "priorities"],
        }

    # =========================================================================
    # Daily Workflow Hooks
    # =========================================================================

    async def _planning_enrichment_hook(
        self,
        ctx: ModuleContext,
    ) -> str | None:
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
    # Data Loading / Persistence Helpers
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

    # =========================================================================
    # Backward-compatible delegating methods (used by tests)
    # =========================================================================

    @staticmethod
    def _parse_priorities(
        message: str, max_priorities: int,
    ) -> list[PriorityItem]:
        """Parse priorities from user message. Delegates to planning_helpers."""
        return _parse_priorities(message, max_priorities)

    @staticmethod
    def _parse_tasks(
        message: str, priorities: list[PriorityItem],
    ) -> list[dict[str, Any]]:
        """Parse tasks from user message. Delegates to planning_helpers."""
        return _parse_tasks(message, priorities)

    @staticmethod
    def _is_sensory_overloaded(message: str) -> bool:
        """Check if user indicates sensory overload. Delegates to planning_helpers."""
        return _is_sensory_overloaded(message)

    @staticmethod
    def _parse_icnu(message: str) -> int:
        """Parse ICNU charge from message. Delegates to planning_helpers."""
        return _parse_icnu(message)

    @staticmethod
    def _parse_channel(message: str) -> str | None:
        """Parse channel dominance from message. Delegates to planning_helpers."""
        return _parse_channel(message)

    @staticmethod
    def _get_segment_guidance(segment: Any) -> str:
        """Get segment-specific guidance text. Delegates to planning_helpers."""
        return _get_segment_guidance(segment)

    @staticmethod
    def _check_integrity(message: str, session: PlanningSession) -> bool:
        """Check if plan aligns with integrity values. Delegates to planning_helpers."""
        return _check_integrity(message, session)


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "PlanningModule",
    "PlanningState",
    "PlanningSession",
    "PriorityItem",
]
