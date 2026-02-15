"""
Milestone Detection for Aurora Agent.

Deterministic milestone detection with segment-specific thresholds:
- pattern_broken: A destructive cycle was interrupted
- belief_refuted: A limiting belief was challenged by evidence
- goal_achieved: A declared goal was completed
- habit_established: A new habit reached the threshold

Threshold rules (from SegmentContext.core.habit_threshold_days):
- ADHD/AuDHD/Neurotypical: 21 days
- Autism: 14 days (routine anchoring makes habits faster)

Reference: ARCHITECTURE.md Section 5 (Aurora Agent - Milestone Detection)
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.core.segment_context import SegmentContext

# Confidence scores for each milestone type
_CONFIDENCE_PATTERN_BROKEN = 0.85
_CONFIDENCE_BELIEF_REFUTED = 0.80
_CONFIDENCE_GOAL_ACHIEVED = 1.0
_CONFIDENCE_HABIT_ESTABLISHED = 0.95

# Mapping from MilestoneType to the metadata key used for deduplication
_MILESTONE_META_KEY: dict[str, str] = {
    "pattern_broken": "pattern_name",
    "belief_refuted": "belief",
    "goal_achieved": "goal_name",
    "habit_established": "habit_name",
}


class MilestoneType(StrEnum):
    """Types of milestones that can be detected."""

    PATTERN_BROKEN = "pattern_broken"
    BELIEF_REFUTED = "belief_refuted"
    GOAL_ACHIEVED = "goal_achieved"
    HABIT_ESTABLISHED = "habit_established"


@dataclass
class MilestoneEvent:
    """A detected milestone event.

    Contains all information about a milestone detection,
    including the evidence that triggered it and the
    segment-specific context.
    """

    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: int = 0
    milestone_type: MilestoneType = MilestoneType.GOAL_ACHIEVED
    title: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0 - 1.0
    segment_code: str = "NT"
    detected_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "milestone_type": self.milestone_type.value,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "segment_code": self.segment_code,
            "detected_at": self.detected_at,
            "metadata": self.metadata,
        }


class MilestoneDetector:
    """Milestone Detection for Aurora Agent.

    Detects significant achievements using deterministic rules.
    All thresholds are segment-specific via SegmentContext.

    Usage:
        detector = MilestoneDetector()
        milestones = detector.check_milestones(user_id=1, segment_ctx=ctx, ...)
    """

    def __init__(self) -> None:
        """Initialize the milestone detector."""
        # In-memory storage (production: PostgreSQL)
        self._detected: dict[int, list[MilestoneEvent]] = {}

    def check_milestones(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        broken_patterns: list[str] | None = None,
        refuted_beliefs: list[str] | None = None,
        achieved_goals: list[str] | None = None,
        habit_streaks: dict[str, int] | None = None,
    ) -> list[MilestoneEvent]:
        """Check for all milestone types.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            broken_patterns: Patterns that were broken (cycle names)
            refuted_beliefs: Beliefs that were refuted by evidence
            achieved_goals: Goals that were completed
            habit_streaks: Dict of habit_name -> consecutive days

        Returns:
            List of newly detected MilestoneEvent objects
        """
        milestones: list[MilestoneEvent] = []

        # Collect milestones from simple list-based detectors
        _detector_items: list[tuple[list[str] | None, str]] = [
            (broken_patterns, "pattern_broken"),
            (refuted_beliefs, "belief_refuted"),
            (achieved_goals, "goal_achieved"),
        ]
        _detect_funcs: dict[str, Callable[[str], MilestoneEvent | None]] = {
            "pattern_broken": lambda item: self.detect_pattern_broken(
                user_id=user_id, segment_ctx=segment_ctx, pattern_name=item,
            ),
            "belief_refuted": lambda item: self.detect_belief_refuted(
                user_id=user_id, segment_ctx=segment_ctx, belief=item,
            ),
            "goal_achieved": lambda item: self.detect_goal_achieved(
                user_id=user_id, segment_ctx=segment_ctx, goal_name=item,
            ),
        }

        for items, kind in _detector_items:
            if items:
                detect = _detect_funcs[kind]
                for item in items:
                    event = detect(item)
                    if event is not None:
                        milestones.append(event)

        # Habit streaks need special handling (dict with days parameter)
        if habit_streaks:
            for habit_name, days in habit_streaks.items():
                event = self.detect_habit_established(
                    user_id=user_id,
                    segment_ctx=segment_ctx,
                    habit_name=habit_name,
                    consecutive_days=days,
                )
                if event is not None:
                    milestones.append(event)

        # Record all detected milestones
        for milestone in milestones:
            self._record_milestone(user_id, milestone)

        return milestones

    def detect_pattern_broken(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        pattern_name: str,
        evidence: list[str] | None = None,
    ) -> MilestoneEvent | None:
        """Detect if a destructive pattern was broken.

        A pattern is considered broken when the user has gone
        at least one full cycle without relapsing.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            pattern_name: Name of the broken pattern
            evidence: Evidence supporting the detection

        Returns:
            MilestoneEvent if detected, None otherwise
        """
        if not pattern_name:
            return None

        # Check for duplicates (same pattern, same user, not already detected)
        if self._is_already_detected(
            user_id, MilestoneType.PATTERN_BROKEN, pattern_name
        ):
            return None

        return MilestoneEvent(
            user_id=user_id,
            milestone_type=MilestoneType.PATTERN_BROKEN,
            title=f"Pattern Broken: {pattern_name}",
            description=(
                f"You broke the {pattern_name} cycle. "
                "This is significant progress."
            ),
            evidence=evidence or [f"Pattern '{pattern_name}' not observed for full cycle"],
            confidence=_CONFIDENCE_PATTERN_BROKEN,
            segment_code=segment_ctx.core.code,
            metadata={"pattern_name": pattern_name},
        )

    def detect_belief_refuted(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        belief: str,
        evidence: list[str] | None = None,
    ) -> MilestoneEvent | None:
        """Detect if a limiting belief was refuted by evidence.

        A belief is considered refuted when the user has acted
        contrary to it at least 3 times.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            belief: The limiting belief that was refuted
            evidence: Evidence that refutes the belief

        Returns:
            MilestoneEvent if detected, None otherwise
        """
        if not belief:
            return None

        if self._is_already_detected(
            user_id, MilestoneType.BELIEF_REFUTED, belief
        ):
            return None

        return MilestoneEvent(
            user_id=user_id,
            milestone_type=MilestoneType.BELIEF_REFUTED,
            title="Belief Challenged",
            description=(
                f'Your actions have challenged the belief: "{belief}". '
                "Evidence suggests a different reality."
            ),
            evidence=evidence or [f"Belief '{belief}' contradicted by user actions"],
            confidence=_CONFIDENCE_BELIEF_REFUTED,
            segment_code=segment_ctx.core.code,
            metadata={"belief": belief},
        )

    def detect_goal_achieved(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        goal_name: str,
        evidence: list[str] | None = None,
    ) -> MilestoneEvent | None:
        """Detect if a declared goal was achieved.

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            goal_name: Name of the achieved goal
            evidence: Evidence of achievement

        Returns:
            MilestoneEvent if detected, None otherwise
        """
        if not goal_name:
            return None

        if self._is_already_detected(
            user_id, MilestoneType.GOAL_ACHIEVED, goal_name
        ):
            return None

        return MilestoneEvent(
            user_id=user_id,
            milestone_type=MilestoneType.GOAL_ACHIEVED,
            title=f"Goal Achieved: {goal_name}",
            description=(
                f"You completed your goal: {goal_name}. "
                "Take a moment to acknowledge this."
            ),
            evidence=evidence or [f"Goal '{goal_name}' marked as completed"],
            confidence=_CONFIDENCE_GOAL_ACHIEVED,
            segment_code=segment_ctx.core.code,
            metadata={"goal_name": goal_name},
        )

    def detect_habit_established(
        self,
        user_id: int,
        segment_ctx: SegmentContext,
        habit_name: str,
        consecutive_days: int,
        evidence: list[str] | None = None,
    ) -> MilestoneEvent | None:
        """Detect if a new habit has been established.

        Uses segment-specific thresholds from SegmentContext:
        - ADHD/AuDHD/Neurotypical: 21 days
        - Autism: 14 days (routine anchoring makes habits faster)

        Args:
            user_id: The user's unique identifier
            segment_ctx: The user's segment context
            habit_name: Name of the habit
            consecutive_days: Number of consecutive days the habit was performed
            evidence: Evidence of habit formation

        Returns:
            MilestoneEvent if threshold met, None otherwise
        """
        if not habit_name:
            return None

        # Use segment-specific threshold
        threshold = segment_ctx.core.habit_threshold_days

        if consecutive_days < threshold:
            return None

        if self._is_already_detected(
            user_id, MilestoneType.HABIT_ESTABLISHED, habit_name
        ):
            return None

        return MilestoneEvent(
            user_id=user_id,
            milestone_type=MilestoneType.HABIT_ESTABLISHED,
            title=f"Habit Established: {habit_name}",
            description=(
                f"You have maintained {habit_name} for "
                f"{consecutive_days} consecutive days. "
                f"The threshold was {threshold} days. This is now a habit."
            ),
            evidence=evidence or [
                f"Habit '{habit_name}' performed for "
                f"{consecutive_days} consecutive days "
                f"(threshold: {threshold})"
            ],
            confidence=_CONFIDENCE_HABIT_ESTABLISHED,
            segment_code=segment_ctx.core.code,
            metadata={
                "habit_name": habit_name,
                "consecutive_days": consecutive_days,
                "threshold_days": threshold,
            },
        )

    def get_milestones(self, user_id: int) -> list[MilestoneEvent]:
        """Get all detected milestones for a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            List of MilestoneEvent objects
        """
        return self._detected.get(user_id, [])

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """GDPR export for milestone data.

        Args:
            user_id: The user's unique identifier

        Returns:
            All milestone data for the user
        """
        milestones = self._detected.get(user_id, [])
        return {
            "milestones": [m.to_dict() for m in milestones],
        }

    def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for milestone data.

        Args:
            user_id: The user's unique identifier
        """
        self._detected.pop(user_id, None)

    def _record_milestone(
        self, user_id: int, event: MilestoneEvent
    ) -> None:
        """Record a detected milestone.

        Args:
            user_id: The user's unique identifier
            event: The milestone event to record
        """
        if user_id not in self._detected:
            self._detected[user_id] = []
        self._detected[user_id].append(event)

    def _is_already_detected(
        self,
        user_id: int,
        milestone_type: MilestoneType,
        identifier: str,
    ) -> bool:
        """Check if a milestone was already detected.

        Prevents duplicate milestone detections for the same achievement.

        Args:
            user_id: The user's unique identifier
            milestone_type: Type of milestone
            identifier: Unique identifier for the specific milestone

        Returns:
            True if already detected, False otherwise
        """
        meta_key = _MILESTONE_META_KEY.get(milestone_type.value)
        if meta_key is None:
            return False

        existing = self._detected.get(user_id, [])
        return any(
            event.milestone_type == milestone_type
            and event.metadata.get(meta_key) == identifier
            for event in existing
        )
