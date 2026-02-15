"""
Daily Workflow Engine for Aurora Sun V1.

The Daily Workflow is a first-class LangGraph -- not something assembled from
calling separate modules. It IS the central user experience.

State Graph:
    morning_activate → neurostate_preflight → vision_display → planning
        → [during_day: reminders + inline_coaching]
        → evening_review → reflect → end

Reference:
- ARCHITECTURE.md Section 3 (Daily Workflow Engine)
- ARCHITECTURE.md SW-1 (Daily Cycle)
- ARCHITECTURE.md SW-12 (Burnout Redirect)
- ARCHITECTURE.md SW-18 (Neurostate Assessment Tiered Pre-Flight)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_response import ModuleResponse
from src.core.segment_context import WorkingStyleCode
from src.lib.security import hash_uid

if TYPE_CHECKING:
    from src.models.daily_plan import DailyPlan
    from src.models.goal import Goal
    from src.models.user import User

logger = logging.getLogger(__name__)


# =============================================================================
# Daily Workflow Triggers
# =============================================================================

class WorkflowTrigger(StrEnum):
    """What triggered the daily workflow."""

    SCHEDULED = "scheduled"  # Segment-adaptive morning time
    MANUAL = "manual"  # User explicitly started
    ONBOARDING = "onboarding"  # First day after onboarding
    RECOVERY = "recovery"  # After burnout/crisis recovery


# =============================================================================
# Daily Workflow Result
# =============================================================================

@dataclass
class DailyWorkflowResult:
    """Result of running the daily workflow.

    Attributes:
        success: Whether the workflow completed successfully
        completed_stages: List of stages that were completed
        skipped_stage: Stage that was skipped (e.g., overload → redirect)
        final_message: Message to send to user
        daily_plan_id: ID of the created/updated DailyPlan record
        redirect_triggered: Whether a redirect was triggered (burnout/crisis)
        redirect_reason: Reason for redirect if triggered
    """

    success: bool
    completed_stages: list[str] = field(default_factory=list)
    skipped_stage: str | None = None
    final_message: str = ""
    daily_plan_id: int | None = None
    redirect_triggered: bool = False
    redirect_reason: str | None = None

    @property
    def was_redirected(self) -> bool:
        """Check if workflow was redirected to recovery."""
        return self.redirect_triggered


# =============================================================================
# Daily Workflow State
# =============================================================================

@dataclass
class DailyWorkflowState:
    """State carried through the daily workflow graph.

    This is the state object used by LangGraph to track progress
    through the daily workflow.

    Attributes:
        user_id: The user ID
        date: The date for this daily plan
        segment_code: User's segment code (AD/AU/AH/NT/CU)
        trigger: What triggered this workflow
        completed_stages: Stages that have been completed
        current_stage: Current stage in the workflow
        energy_level: Energy level from morning check (1-5)
        overload_detected: Whether overload was detected
        vision_displayed: Whether vision was shown
        goals_reviewed: Whether goals were reviewed
        planning_completed: Whether planning was completed
        midday_completed: Whether midday check-in happened
        evening_completed: Whether evening review happened
        reflection_text: User's reflection text
        tomorrow_intention: User's intention for tomorrow
        interventions_delivered: List of interventions delivered today
    """

    # Identity
    user_id: int
    date: date
    segment_code: WorkingStyleCode
    trigger: WorkflowTrigger = WorkflowTrigger.SCHEDULED

    # Progress tracking
    completed_stages: list[str] = field(default_factory=list)
    current_stage: str = "morning_activate"

    # Neurostate
    energy_level: int | None = None
    sensory_load: float | None = None
    burnout_risk: float | None = None
    overload_detected: bool = False

    # Daily workflow flags
    vision_displayed: bool = False
    goals_reviewed: bool = False
    planning_completed: bool = False
    midday_completed: bool = False
    evening_completed: bool = False

    # Reflection
    reflection_text: str | None = None
    tomorrow_intention: str | None = None

    # Tracking
    interventions_delivered: list[str] = field(default_factory=list)

    # Result (populated at end)
    result: DailyWorkflowResult | None = None


# =============================================================================
# Segment-Adaptive Timing Configuration
# =============================================================================

@dataclass
class SegmentTimingConfig:
    """Segment-adaptive timing for daily workflow events.

    Reference: ARCHITECTURE.md Section 3
    """

    # Morning activation time (required)
    morning_hour: int
    morning_minute: int

    # Midday check-in timing strategy (required)
    midday_strategy: str  # interval | exact_time | semi_predictable

    # Evening review time (required)
    evening_hour: int
    evening_minute: int

    # Exact time for Autism (if exact_time strategy) - optional
    midday_exact_hour: int | None = None
    midday_exact_minute: int | None = None

    # Interval for ADHD (in minutes, after last interaction) - optional
    midday_interval_minutes: int | None = None

    # Evening reflection cutoff (after which we don't prompt)
    reflection_cutoff_hour: int = 22


# Segment-adaptive timing configurations
SEGMENT_TIMING_CONFIGS: dict[WorkingStyleCode, SegmentTimingConfig] = {
    "AD": SegmentTimingConfig(
        morning_hour=8,
        morning_minute=0,
        midday_strategy="interval",
        midday_interval_minutes=90,  # 90 min after last interaction
        evening_hour=20,
        evening_minute=0,
    ),
    "AU": SegmentTimingConfig(
        morning_hour=9,
        morning_minute=0,
        midday_strategy="exact_time",
        midday_exact_hour=13,
        midday_exact_minute=0,
        evening_hour=19,
        evening_minute=0,
    ),
    "AH": SegmentTimingConfig(
        morning_hour=8,
        morning_minute=30,
        midday_strategy="semi_predictable",
        midday_interval_minutes=60,  # Flexible, depends on channel dominance
        evening_hour=19,
        evening_minute=30,
    ),
    "NT": SegmentTimingConfig(
        morning_hour=8,
        morning_minute=0,
        midday_strategy="interval",
        midday_interval_minutes=120,
        evening_hour=20,
        evening_minute=0,
    ),
    "CU": SegmentTimingConfig(
        morning_hour=8,
        morning_minute=0,
        midday_strategy="interval",
        midday_interval_minutes=120,
        evening_hour=20,
        evening_minute=0,
    ),
}


# =============================================================================
# Daily Workflow Engine
# =============================================================================

class DailyWorkflow:
    """
    The Daily Workflow Engine orchestrates the daily planning cycle.

    This is NOT assembled from module calls -- it IS the central user
    experience, implemented as a first-class LangGraph.

    State Graph:
        morning_activate → neurostate_preflight → vision_display → planning
            → [during_day: reminders + inline_coaching]
            → evening_review → reflect → end

    Key Features:
    - Morning activation: vision + energy check + yesterday's wins
    - Tiered neurostate pre-flight (always 1Q, +sensory if yellow, full if red)
    - Overload detection → gentle redirect to recovery
    - Vision display: show vision + 90d goals
    - Planning: invoke Planning Module
    - CheckinScheduler: segment-adaptive timing
    - Evening: auto-trigger Review Module
    - Reflection: energy + 1-line reflection + tomorrow intention
    - Save DailyPlan record
    - Feed Aurora narrative update
    """

    def __init__(self) -> None:
        """Initialize the Daily Workflow Engine."""
        self._hooks: dict[str, DailyWorkflowHooks] = {}
        logger.info("DailyWorkflow engine initialized")

    def register_module_hooks(self, module_name: str, hooks: DailyWorkflowHooks) -> None:
        """Register daily workflow hooks from a module.

        Args:
            module_name: Name of the module
            hooks: DailyWorkflowHooks from the module
        """
        self._hooks[module_name] = hooks
        logger.debug("Registered daily workflow hooks from module: %s", module_name)

    def get_timing_config(self, segment_code: WorkingStyleCode) -> SegmentTimingConfig:
        """Get segment-adaptive timing configuration.

        Args:
            segment_code: User's segment code

        Returns:
            SegmentTimingConfig for the segment
        """
        return SEGMENT_TIMING_CONFIGS.get(
            segment_code,
            SEGMENT_TIMING_CONFIGS["NT"]  # Default to NT
        )

    def get_morning_time(self, segment_code: WorkingStyleCode) -> time:
        """Get segment-adaptive morning activation time.

        Args:
            segment_code: User's segment code

        Returns:
            time object for morning activation
        """
        config = self.get_timing_config(segment_code)
        return time(hour=config.morning_hour, minute=config.morning_minute)

    def get_midday_time(self, segment_code: WorkingStyleCode) -> time | None:
        """Get segment-adaptive midday check-in time.

        For ADHD: returns None (interval-based, not time-based)
        For Autism: returns exact time
        For AuDHD: returns None (semi-predictable, channel-dependent)

        Args:
            segment_code: User's segment code

        Returns:
            time object for midday check-in, or None if interval-based
        """
        config = self.get_timing_config(segment_code)

        if config.midday_strategy == "exact_time" and config.midday_exact_hour is not None:
            return time(
                hour=config.midday_exact_hour,
                minute=config.midday_exact_minute or 0
            )

        return None

    def get_midday_interval(self, segment_code: WorkingStyleCode) -> int | None:
        """Get segment-adaptive midday interval in minutes.

        Returns interval for ADHD/AuDHD, None for Autism (time-based).

        Args:
            segment_code: User's segment code

        Returns:
            Interval in minutes, or None if time-based
        """
        config = self.get_timing_config(segment_code)

        if config.midday_strategy == "interval":
            return config.midday_interval_minutes

        return None

    def get_evening_time(self, segment_code: WorkingStyleCode) -> time:
        """Get segment-adaptive evening review time.

        Args:
            segment_code: User's segment code

        Returns:
            time object for evening review
        """
        config = self.get_timing_config(segment_code)
        return time(hour=config.evening_hour, minute=config.evening_minute)

    async def run(
        self,
        user_id: int,
        trigger: str = "scheduled",
        user: User | None = None,
    ) -> DailyWorkflowResult:
        """
        Run the complete daily workflow for a user.

        This is the main entry point. It orchestrates all stages:
        1. Morning activation: vision + energy check + yesterday's wins
        2. NeurostateService: tiered pre-flight
        3. IF overload → gentle redirect (no planning)
        4. Vision display: show vision + 90d goals
        5. Planning: invoke Planning Module
        6. During day: CheckinScheduler with segment-adaptive timing
        7. Evening: auto-trigger Review Module
        8. Reflect: energy + 1-line reflection + tomorrow intention
        9. Save DailyPlan record
        10. Feed Aurora (narrative update)

        Args:
            user_id: The user ID
            trigger: What triggered this workflow (scheduled, manual, onboarding, recovery)
            user: Optional pre-loaded user object (for efficiency)

        Returns:
            DailyWorkflowResult with completion status and details
        """
        # Determine trigger type
        trigger_enum = WorkflowTrigger(trigger) if trigger in [t.value for t in WorkflowTrigger] else WorkflowTrigger.MANUAL

        # Get segment context
        segment_code: WorkingStyleCode = "NT"
        if user:
            # working_style_code is Column[str] | None at class level, str | None at runtime
            raw_code = str(user.working_style_code) if user.working_style_code else None
            # Cast to WorkingStyleCode if valid, otherwise default to NT
            from typing import cast
            segment_code = cast(WorkingStyleCode, raw_code) if raw_code in ("AD", "AU", "AH", "NT", "CU") else "NT"

        # Initialize workflow state
        DailyWorkflowState(
            user_id=user_id,
            date=date.today(),
            segment_code=segment_code,
            trigger=trigger_enum,
        )

        # TODO: Run through LangGraph (daily_graph.py)
        # For now, we'll use this as the orchestrator
        # The actual graph execution will be in daily_graph.py

        result = DailyWorkflowResult(
            success=True,
            completed_stages=["morning_activate", "neurostate_preflight"],
            final_message="Daily workflow completed",
        )

        logger.info("Daily workflow completed for user_hash=%s: %s", hash_uid(user_id), result.completed_stages)
        return result

    async def run_morning_activation(
        self,
        user_id: int,
        segment_code: WorkingStyleCode,
    ) -> tuple[str, list[str]]:
        """
        Run morning activation stage.

        Morning activation includes:
        - Vision reminder
        - Energy check (tiered based on segment)
        - Yesterday's wins (if available)

        Args:
            user_id: The user ID
            segment_code: User's segment code

        Returns:
            Tuple of (message, list of interventions delivered)
        """
        interventions: list[str] = []

        # Build morning message
        messages: list[str] = []

        # TODO: Get yesterday's wins from DailyPlan

        # TODO: Call morning hooks from registered modules

        message = "\n".join(messages) if messages else "Good morning! Let's start your day."

        # F-010: Log metadata only, not message content
        logger.info("Morning activation for user_hash=%s: message_len=%d, interventions=%d", hash_uid(user_id), len(message), len(interventions))
        return message, interventions

    async def run_neurostate_preflight(
        self,
        user_id: int,
        segment_code: WorkingStyleCode,
        previous_energy: int | None = None,
        consecutive_red_days: int = 0,
    ) -> tuple[dict[str, Any], bool]:
        """
        Run tiered neurostate pre-flight.

        Reference: SW-18 (Neurostate Assessment Tiered Pre-Flight)

        TIER 1 (ALWAYS):
          - 1-question energy check
          - ADHD/Neurotypical: self-report
          - Autism/AuDHD: behavioral proxy

        TIER 2 (YELLOW energy OR segment requires):
          - + Sensory State Assessment (AU/AH)
          - + Channel Dominance Detection (AH only)

        TIER 3 (RED energy OR 3+ consecutive red days):
          - + Full assessment: sensory + masking + burnout trajectory
          - + Inertia Detection (type-specific)

        TIER 4 (AU/AH + afternoon):
          - Sensory accumulation check

        Args:
            user_id: The user ID
            segment_code: User's segment code
            previous_energy: Previous day's energy level
            consecutive_red_days: Number of consecutive red energy days

        Returns:
            Tuple of (neurostate_snapshot, overload_detected)
        """
        # Determine tier based on conditions
        tier = 1

        # Yellow energy triggers Tier 2
        if previous_energy is not None and previous_energy <= 2:
            tier = max(tier, 2)

        # Red energy or 3+ red days triggers Tier 3
        if (previous_energy is not None and previous_energy == 1) or consecutive_red_days >= 3:
            tier = max(tier, 3)

        # Build neurostate snapshot based on tier
        snapshot: dict[str, Any] = {
            "tier": tier,
            "energy_level": None,  # Will be filled by actual assessment
            "sensory_load": None,
            "masking_cost": None,
            "burnout_risk": None,
        }

        # Determine if overload is detected
        overload_detected = snapshot.get("burnout_risk", 0) > 0.8 if snapshot.get("burnout_risk") else False

        logger.info("Neurostate pre-flight for user_hash=%s: tier=%d, overload=%s", hash_uid(user_id), tier, overload_detected)
        return snapshot, overload_detected

    async def checkin_scheduler(
        self,
        user_id: int,
        segment_code: WorkingStyleCode,
    ) -> time | None:
        """
        Get segment-adaptive check-in time for midday reminder.

        Reference: ARCHITECTURE.md Section 3

        - ADHD: interval-based (90 min after last interaction)
        - Autism: exact time (13:00)
        - AuDHD: semi-predictable (channel-dependent)

        Args:
            user_id: The user ID
            segment_code: User's segment code

        Returns:
            time for midday check-in, or None if interval-based
        """
        return self.get_midday_time(segment_code)

    async def gentle_redirect(
        self,
        user_id: int,
        reason: str,
    ) -> ModuleResponse:
        """
        Handle overload → gentle redirect to recovery.

        When burnout or overload is detected, we don't proceed with
        planning. Instead, we redirect to a recovery protocol.

        Reference: SW-12 (Burnout Redirect)

        Args:
            user_id: The user ID
            reason: Reason for redirect (e.g., "overload_detected", "burnout_risk")

        Returns:
            ModuleResponse with recovery message
        """
        # Recovery message (segment-adaptive)
        message = (
            "It sounds like you need rest today. That's completely okay.\n\n"
            "Let's focus on recovery instead of planning. Your energy is valuable, "
            "and sometimes the best thing we can do is simply rest.\n\n"
            "I'll check in with you later. Take care of yourself."
        )

        logger.info("Gentle redirect for user_hash=%s: %s", hash_uid(user_id), reason)

        return ModuleResponse(
            text=message,
            is_end_of_flow=True,
            metadata={
                "redirect": True,
                "reason": reason,
                "daily_workflow_stage": "gentle_redirect",
            },
        )

    async def run_vision_display(
        self,
        user_id: int,
    ) -> tuple[list[str], list[Goal]]:
        """
        Display vision and 90-day goals to the user.

        Args:
            user_id: The user ID

        Returns:
            Tuple of (vision_texts, goals)
        """
        # TODO: Load vision and goals from database

        visions: list[str] = []
        goals: list[Goal] = []

        logger.info("Vision display for user_hash=%s", hash_uid(user_id))
        return visions, goals

    async def run_evening_review(
        self,
        user_id: int,
    ) -> ModuleResponse:
        """
        Run evening review (auto-triggered).

        This is called automatically at the segment-adaptive evening time,
        not manually by the user.

        Reference: SW-1 step 10

        Args:
            user_id: The user ID

        Returns:
            ModuleResponse for evening review
        """
        # TODO: Invoke Review Module
        # For now, return a placeholder
        message = "It's evening! Let's review your day."

        logger.info("Evening review triggered for user_hash=%s", hash_uid(user_id))

        return ModuleResponse(
            text=message,
            metadata={
                "daily_workflow_stage": "evening_review",
                "auto_triggered": True,
            },
        )

    async def run_reflection(
        self,
        user_id: int,
        segment_code: WorkingStyleCode,
    ) -> tuple[int, str, str]:
        """
        Run end-of-day reflection.

        Reflection includes:
        - Energy check (1-5)
        - 1-line reflection on the day
        - Tomorrow's intention

        Args:
            user_id: The user ID
            segment_code: User's segment code

        Returns:
            Tuple of (evening_energy, reflection_text, tomorrow_intention)
        """
        # TODO: Prompt user for reflection
        # This would be handled by the bot interface

        logger.info("Reflection completed for user_hash=%s", hash_uid(user_id))
        return 0, "", ""

    async def save_daily_plan(
        self,
        user_id: int,
        date: date,
        state: DailyWorkflowState,
    ) -> DailyPlan:
        """
        Save the daily plan record.

        Args:
            user_id: The user ID
            date: The date for this plan
            state: The workflow state

        Returns:
            Created DailyPlan record
        """
        # TODO: Save to database using SQLAlchemy
        # This requires a database session

        logger.info("Saving daily plan for user_hash=%s on %s", hash_uid(user_id), date)
        raise NotImplementedError("Database session not yet implemented")

    def get_hooks_for_stage(self, stage: str) -> list[tuple[str, DailyWorkflowHooks]]:
        """Get all hooks for a specific workflow stage.

        Args:
            stage: The workflow stage (morning, planning_enrichment, midday_check, evening_review)

        Returns:
            List of (module_name, hooks) tuples that have hooks for this stage
        """
        results: list[tuple[str, DailyWorkflowHooks]] = []

        for module_name, hooks in self._hooks.items():
            if stage == "morning" and hooks.morning:
                results.append((module_name, hooks))
            elif stage == "planning_enrichment" and hooks.planning_enrichment:
                results.append((module_name, hooks))
            elif stage == "midday_check" and hooks.midday_check:
                results.append((module_name, hooks))
            elif stage == "evening_review" and hooks.evening_review:
                results.append((module_name, hooks))

        # Sort by priority
        results.sort(key=lambda x: x[1].priority)
        return results


# =============================================================================
# Global Instance
# =============================================================================

# Global daily workflow instance
_daily_workflow: DailyWorkflow | None = None


def get_daily_workflow() -> DailyWorkflow:
    """Get the global DailyWorkflow instance.

    Returns:
        The global DailyWorkflow instance
    """
    global _daily_workflow
    if _daily_workflow is None:
        _daily_workflow = DailyWorkflow()
    return _daily_workflow


__all__ = [
    "DailyWorkflow",
    "DailyWorkflowState",
    "DailyWorkflowResult",
    "WorkflowTrigger",
    "SegmentTimingConfig",
    "get_daily_workflow",
]
