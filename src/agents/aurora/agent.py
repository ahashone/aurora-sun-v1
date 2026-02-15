"""
Aurora Agent - Main Synthesis Intelligence Layer.

The Aurora Agent orchestrates the weekly cycle:
    Gather -> Assess -> Synthesize -> Recommend -> (Error handling)

It coordinates between sub-engines:
- NarrativeEngine: Story arcs and chapters
- GrowthTracker: 5-dimension trajectory scoring
- MilestoneDetector: Deterministic milestone detection
- CoherenceAuditor: Vision-Goal-Habit alignment
- ProactiveEngine: Readiness-based impulse delivery

The agent operates in observation mode by default:
- It OBSERVES and THINKS autonomously
- It PROPOSES actions for admin approval
- It NEVER acts without approval

Reference: ARCHITECTURE.md Section 5 (Aurora Agent)
Reference: ARCHITECTURE.md Section 11 (Autonomy Framework)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext

from .coherence import CoherenceAuditor, CoherenceResult
from .growth import GrowthSummary, GrowthTracker, TrajectoryScore
from .milestones import MilestoneDetector, MilestoneEvent
from .narrative import Chapter, MilestoneCard, NarrativeEngine
from .proactive import ProactiveEngine, ProactiveImpulse, ReadinessScore


class WorkflowStep(StrEnum):
    """Steps in the Aurora weekly cycle workflow."""

    GATHER = "gather"
    ASSESS = "assess"
    SYNTHESIZE = "synthesize"
    RECOMMEND = "recommend"
    ERROR = "error"
    COMPLETE = "complete"


@dataclass
class AuroraState:
    """State of the Aurora Agent workflow.

    Tracks the current step, accumulated data, and results
    through the Gather -> Assess -> Synthesize -> Recommend cycle.
    """

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    current_step: WorkflowStep = WorkflowStep.GATHER
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    # Gathered data
    broken_patterns: list[str] = field(default_factory=list)
    refuted_beliefs: list[str] = field(default_factory=list)
    achieved_goals: list[str] = field(default_factory=list)
    habit_streaks: dict[str, int] = field(default_factory=dict)
    vision: str = ""
    goals: list[str] = field(default_factory=list)
    habits: list[str] = field(default_factory=list)
    goal_habit_links: dict[str, list[str]] = field(default_factory=dict)

    # Assessment results
    trajectory: TrajectoryScore | None = None
    milestones: list[MilestoneEvent] = field(default_factory=list)
    coherence: CoherenceResult | None = None

    # Synthesis results
    chapter: Chapter | None = None
    growth_summary: GrowthSummary | None = None

    # Recommendations
    impulses: list[ProactiveImpulse] = field(default_factory=list)
    readiness: ReadinessScore | None = None

    # Error tracking
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "user_id": self.user_id,
            "current_step": self.current_step.value,
            "started_at": self.started_at,
            "milestones_count": len(self.milestones),
            "has_chapter": self.chapter is not None,
            "has_growth_summary": self.growth_summary is not None,
            "impulses_count": len(self.impulses),
            "errors": self.errors,
        }


class AuroraAgent:
    """Aurora Agent - Synthesis Intelligence Layer.

    Orchestrates the weekly cycle and coordinates sub-engines.
    Observes, thinks, and proposes. Never acts autonomously.

    Usage:
        agent = AuroraAgent()
        state = await agent.run_weekly_cycle(user_id=1, segment_ctx=ctx, ...)
    """

    def __init__(
        self,
        narrative_engine: NarrativeEngine | None = None,
        growth_tracker: GrowthTracker | None = None,
        milestone_detector: MilestoneDetector | None = None,
        coherence_auditor: CoherenceAuditor | None = None,
        proactive_engine: ProactiveEngine | None = None,
    ) -> None:
        """Initialize the Aurora Agent.

        Args:
            narrative_engine: Optional NarrativeEngine instance
            growth_tracker: Optional GrowthTracker instance
            milestone_detector: Optional MilestoneDetector instance
            coherence_auditor: Optional CoherenceAuditor instance
            proactive_engine: Optional ProactiveEngine instance
        """
        self.narrative = narrative_engine or NarrativeEngine()
        self.growth = growth_tracker or GrowthTracker()
        self.milestones = milestone_detector or MilestoneDetector()
        self.coherence = coherence_auditor or CoherenceAuditor()
        self.proactive = proactive_engine or ProactiveEngine()

    async def run_weekly_cycle(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        vision: str = "",
        goals: list[str] | None = None,
        habits: list[str] | None = None,
        goal_habit_links: dict[str, list[str]] | None = None,
        broken_patterns: list[str] | None = None,
        refuted_beliefs: list[str] | None = None,
        achieved_goals: list[str] | None = None,
        habit_streaks: dict[str, int] | None = None,
        current_energy: float = 0.5,
        week_number: int = 1,
    ) -> AuroraState:
        """Run the full weekly cycle: Gather -> Assess -> Synthesize -> Recommend.

        This is the main entry point for the Aurora Agent's weekly processing.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            vision: The user's vision statement
            goals: List of goal names
            habits: List of habit names
            goal_habit_links: Dict mapping goal -> supporting habits
            broken_patterns: Patterns broken this week
            refuted_beliefs: Beliefs refuted this week
            achieved_goals: Goals achieved this week
            habit_streaks: Dict of habit_name -> consecutive days
            current_energy: Current energy level (0.0-1.0)
            week_number: Current week number

        Returns:
            AuroraState with all results
        """
        state = AuroraState(user_id=user_id)

        # Step 1: GATHER
        state = await self._gather(
            state=state,
            vision=vision,
            goals=goals or [],
            habits=habits or [],
            goal_habit_links=goal_habit_links or {},
            broken_patterns=broken_patterns or [],
            refuted_beliefs=refuted_beliefs or [],
            achieved_goals=achieved_goals or [],
            habit_streaks=habit_streaks or {},
        )

        # Step 2: ASSESS
        state = await self._assess(state, segment_ctx)

        # Step 3: SYNTHESIZE
        state = await self._synthesize(state, segment_ctx, week_number)

        # Step 4: RECOMMEND
        state = await self._recommend(state, segment_ctx, current_energy)

        state.current_step = WorkflowStep.COMPLETE
        return state

    async def generate_chapter(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        week_number: int,
        milestones: list[MilestoneEvent] | None = None,
    ) -> Chapter:
        """Generate a weekly chapter for the user's narrative.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            week_number: The week number
            milestones: Milestones achieved this week

        Returns:
            The generated Chapter
        """
        # Convert milestones to MilestoneCards
        milestone_cards: list[MilestoneCard] = []
        if milestones:
            for ms in milestones:
                card = self.narrative.detect_milestone(
                    user_id=user_id,
                    milestone_type=ms.milestone_type.value,
                    title=ms.title,
                    description=ms.description,
                )
                milestone_cards.append(card)

        return self.narrative.create_chapter(
            user_id=user_id,
            week_number=week_number,
            milestones=milestone_cards,
        )

    async def check_milestones(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        broken_patterns: list[str] | None = None,
        refuted_beliefs: list[str] | None = None,
        achieved_goals: list[str] | None = None,
        habit_streaks: dict[str, int] | None = None,
    ) -> list[MilestoneEvent]:
        """Check for milestones.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            broken_patterns: Patterns broken
            refuted_beliefs: Beliefs refuted
            achieved_goals: Goals achieved
            habit_streaks: Habit streaks (name -> days)

        Returns:
            List of detected MilestoneEvent objects
        """
        return self.milestones.check_milestones(
            user_id=user_id,
            segment_ctx=segment_ctx,
            broken_patterns=broken_patterns,
            refuted_beliefs=refuted_beliefs,
            achieved_goals=achieved_goals,
            habit_streaks=habit_streaks,
        )

    async def assess_growth(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
    ) -> GrowthSummary:
        """Assess user growth.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context

        Returns:
            GrowthSummary with trajectory and comparisons
        """
        return self.growth.get_growth_summary(
            user_id=user_id,
            segment_ctx=segment_ctx,
        )

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for all Aurora Agent data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All Aurora Agent data for the user
        """
        return {
            "narrative": self.narrative.export_user_data(user_id),
            "growth": self.growth.export_user_data(user_id),
            "milestones": self.milestones.export_user_data(user_id),
            "coherence": self.coherence.export_user_data(user_id),
            "proactive": self.proactive.export_user_data(user_id),
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for all Aurora Agent data.

        Args:
            user_id: The user's unique identifier
        """
        self.narrative.delete_user_data(user_id)
        self.growth.delete_user_data(user_id)
        self.milestones.delete_user_data(user_id)
        self.coherence.delete_user_data(user_id)
        self.proactive.delete_user_data(user_id)

    # ------------------------------------------------------------------
    # Private workflow step methods
    # ------------------------------------------------------------------

    async def _gather(
        self,
        state: AuroraState,
        vision: str,
        goals: list[str],
        habits: list[str],
        goal_habit_links: dict[str, list[str]],
        broken_patterns: list[str],
        refuted_beliefs: list[str],
        achieved_goals: list[str],
        habit_streaks: dict[str, int],
    ) -> AuroraState:
        """Gather step: collect all relevant user data.

        Args:
            state: Current Aurora state
            vision: User's vision
            goals: User's goals
            habits: User's habits
            goal_habit_links: Goal-habit mappings
            broken_patterns: Patterns broken this week
            refuted_beliefs: Beliefs refuted this week
            achieved_goals: Goals achieved this week
            habit_streaks: Habit streaks

        Returns:
            Updated AuroraState
        """
        state.current_step = WorkflowStep.GATHER
        state.vision = vision
        state.goals = goals
        state.habits = habits
        state.goal_habit_links = goal_habit_links
        state.broken_patterns = broken_patterns
        state.refuted_beliefs = refuted_beliefs
        state.achieved_goals = achieved_goals
        state.habit_streaks = habit_streaks
        return state

    async def _assess(
        self,
        state: AuroraState,
        segment_ctx: SegmentContext,
    ) -> AuroraState:
        """Assess step: analyze gathered data.

        Runs milestone detection, coherence audit, and growth trajectory.

        Args:
            state: Current Aurora state
            segment_ctx: The user's segment context

        Returns:
            Updated AuroraState
        """
        state.current_step = WorkflowStep.ASSESS

        try:
            # Check milestones
            state.milestones = self.milestones.check_milestones(
                user_id=state.user_id,
                segment_ctx=segment_ctx,
                broken_patterns=state.broken_patterns,
                refuted_beliefs=state.refuted_beliefs,
                achieved_goals=state.achieved_goals,
                habit_streaks=state.habit_streaks,
            )

            # Run coherence audit
            state.coherence = self.coherence.audit_coherence(
                user_id=state.user_id,
                segment_ctx=segment_ctx,
                vision=state.vision,
                goals=state.goals,
                habits=state.habits,
                goal_habit_links=state.goal_habit_links,
            )

            # Calculate trajectory
            state.trajectory = self.growth.calculate_trajectory(
                user_id=state.user_id,
                segment_ctx=segment_ctx,
            )

        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            state.errors.append(f"Assessment error: {e!s}")
            state.current_step = WorkflowStep.ERROR

        return state

    async def _synthesize(
        self,
        state: AuroraState,
        segment_ctx: SegmentContext,
        week_number: int,
    ) -> AuroraState:
        """Synthesize step: create narrative and growth summary.

        Args:
            state: Current Aurora state
            segment_ctx: The user's segment context
            week_number: Current week number

        Returns:
            Updated AuroraState
        """
        state.current_step = WorkflowStep.SYNTHESIZE

        try:
            # Generate chapter
            milestone_cards: list[MilestoneCard] = []
            for ms in state.milestones:
                card = self.narrative.detect_milestone(
                    user_id=state.user_id,
                    milestone_type=ms.milestone_type.value,
                    title=ms.title,
                    description=ms.description,
                )
                milestone_cards.append(card)

            state.chapter = self.narrative.create_chapter(
                user_id=state.user_id,
                week_number=week_number,
                milestones=milestone_cards,
            )

            # Generate growth summary
            state.growth_summary = self.growth.get_growth_summary(
                user_id=state.user_id,
                segment_ctx=segment_ctx,
                current=state.trajectory,
            )

        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            state.errors.append(f"Synthesis error: {e!s}")
            state.current_step = WorkflowStep.ERROR

        return state

    async def _recommend(
        self,
        state: AuroraState,
        segment_ctx: SegmentContext,
        current_energy: float,
    ) -> AuroraState:
        """Recommend step: generate proactive impulses.

        Args:
            state: Current Aurora state
            segment_ctx: The user's segment context
            current_energy: Current energy level

        Returns:
            Updated AuroraState
        """
        state.current_step = WorkflowStep.RECOMMEND

        try:
            # Calculate readiness
            state.readiness = self.proactive.calculate_readiness(
                user_id=state.user_id,
                segment_ctx=segment_ctx,
                current_energy=current_energy,
                current_hour=12,  # Default to noon for weekly cycle
            )

            # Get pending impulses
            state.impulses = self.proactive.get_pending_impulses(
                state.user_id
            )

        except (ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            state.errors.append(f"Recommendation error: {e!s}")
            state.current_step = WorkflowStep.ERROR

        return state
