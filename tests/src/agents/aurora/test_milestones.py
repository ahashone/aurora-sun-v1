"""
Tests for the Milestone Detector.

Covers:
- All 4 milestone types (pattern_broken, belief_refuted, goal_achieved, habit_established)
- Segment-specific habit thresholds (21d vs 14d)
- Duplicate detection prevention
- Edge cases (empty inputs, boundary values)
- check_milestones integration
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.agents.aurora.milestones import (
    MilestoneDetector,
    MilestoneType,
)
from src.core.segment_context import SegmentContext


@pytest.fixture()
def detector() -> MilestoneDetector:
    """Create a MilestoneDetector instance."""
    return MilestoneDetector()


@pytest.fixture()
def ad_ctx() -> SegmentContext:
    return SegmentContext.from_code("AD")


@pytest.fixture()
def au_ctx() -> SegmentContext:
    return SegmentContext.from_code("AU")


@pytest.fixture()
def ah_ctx() -> SegmentContext:
    return SegmentContext.from_code("AH")


@pytest.fixture()
def nt_ctx() -> SegmentContext:
    return SegmentContext.from_code("NT")


# ============================================================================
# detect_pattern_broken tests
# ============================================================================


class TestPatternBroken:
    def test_detect_basic(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_pattern_broken(
            user_id=1, segment_ctx=nt_ctx, pattern_name="perfectionism"
        )
        assert event is not None
        assert event.milestone_type == MilestoneType.PATTERN_BROKEN
        assert "perfectionism" in event.title

    def test_detect_with_evidence(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_pattern_broken(
            user_id=1,
            segment_ctx=nt_ctx,
            pattern_name="shiny_object",
            evidence=["Stayed with project for 3 weeks"],
        )
        assert event is not None
        assert "Stayed with project" in event.evidence[0]

    def test_empty_pattern_returns_none(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_pattern_broken(
            user_id=1, segment_ctx=nt_ctx, pattern_name=""
        )
        assert event is None

    def test_duplicate_prevention(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event1 = detector.detect_pattern_broken(
            user_id=1, segment_ctx=nt_ctx, pattern_name="isolation"
        )
        # Record the first one
        detector._record_milestone(1, event1)  # type: ignore[arg-type]
        event2 = detector.detect_pattern_broken(
            user_id=1, segment_ctx=nt_ctx, pattern_name="isolation"
        )
        assert event2 is None


# ============================================================================
# detect_belief_refuted tests
# ============================================================================


class TestBeliefRefuted:
    def test_detect_basic(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_belief_refuted(
            user_id=1,
            segment_ctx=nt_ctx,
            belief="I can never finish anything",
        )
        assert event is not None
        assert event.milestone_type == MilestoneType.BELIEF_REFUTED
        assert "I can never finish anything" in event.description

    def test_empty_belief_returns_none(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_belief_refuted(
            user_id=1, segment_ctx=nt_ctx, belief=""
        )
        assert event is None


# ============================================================================
# detect_goal_achieved tests
# ============================================================================


class TestGoalAchieved:
    def test_detect_basic(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_goal_achieved(
            user_id=1, segment_ctx=nt_ctx, goal_name="Launch website"
        )
        assert event is not None
        assert event.milestone_type == MilestoneType.GOAL_ACHIEVED
        assert event.confidence == 1.0

    def test_empty_goal_returns_none(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_goal_achieved(
            user_id=1, segment_ctx=nt_ctx, goal_name=""
        )
        assert event is None

    def test_duplicate_prevention(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event1 = detector.detect_goal_achieved(
            user_id=1, segment_ctx=nt_ctx, goal_name="Ship MVP"
        )
        detector._record_milestone(1, event1)  # type: ignore[arg-type]
        event2 = detector.detect_goal_achieved(
            user_id=1, segment_ctx=nt_ctx, goal_name="Ship MVP"
        )
        assert event2 is None


# ============================================================================
# detect_habit_established tests
# ============================================================================


class TestHabitEstablished:
    def test_adhd_threshold_21_days(
        self, detector: MilestoneDetector, ad_ctx: SegmentContext
    ) -> None:
        """ADHD threshold is 21 days."""
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=ad_ctx,
            habit_name="morning_walk", consecutive_days=21,
        )
        assert event is not None
        assert event.metadata["threshold_days"] == 21

    def test_adhd_below_threshold(
        self, detector: MilestoneDetector, ad_ctx: SegmentContext
    ) -> None:
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=ad_ctx,
            habit_name="morning_walk", consecutive_days=20,
        )
        assert event is None

    def test_autism_threshold_14_days(
        self, detector: MilestoneDetector, au_ctx: SegmentContext
    ) -> None:
        """Autism threshold is 14 days (routine anchoring)."""
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=au_ctx,
            habit_name="journaling", consecutive_days=14,
        )
        assert event is not None
        assert event.metadata["threshold_days"] == 14

    def test_autism_below_threshold(
        self, detector: MilestoneDetector, au_ctx: SegmentContext
    ) -> None:
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=au_ctx,
            habit_name="journaling", consecutive_days=13,
        )
        assert event is None

    def test_audhd_threshold_21_days(
        self, detector: MilestoneDetector, ah_ctx: SegmentContext
    ) -> None:
        """AuDHD threshold is 21 days."""
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=ah_ctx,
            habit_name="meditation", consecutive_days=21,
        )
        assert event is not None
        assert event.metadata["threshold_days"] == 21

    def test_nt_threshold_21_days(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        """NT threshold is 21 days."""
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=nt_ctx,
            habit_name="exercise", consecutive_days=21,
        )
        assert event is not None

    def test_empty_habit_returns_none(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=nt_ctx,
            habit_name="", consecutive_days=30,
        )
        assert event is None

    def test_above_threshold_succeeds(
        self, detector: MilestoneDetector, au_ctx: SegmentContext
    ) -> None:
        """Days above threshold should still detect."""
        event = detector.detect_habit_established(
            user_id=1, segment_ctx=au_ctx,
            habit_name="reading", consecutive_days=30,
        )
        assert event is not None
        assert event.metadata["consecutive_days"] == 30


# ============================================================================
# check_milestones integration tests
# ============================================================================


class TestCheckMilestones:
    def test_check_all_types(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        milestones = detector.check_milestones(
            user_id=1,
            segment_ctx=nt_ctx,
            broken_patterns=["isolation"],
            refuted_beliefs=["I always fail"],
            achieved_goals=["Launch MVP"],
            habit_streaks={"journaling": 25},
        )
        types = {m.milestone_type for m in milestones}
        assert MilestoneType.PATTERN_BROKEN in types
        assert MilestoneType.BELIEF_REFUTED in types
        assert MilestoneType.GOAL_ACHIEVED in types
        assert MilestoneType.HABIT_ESTABLISHED in types

    def test_check_no_milestones(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        milestones = detector.check_milestones(
            user_id=1, segment_ctx=nt_ctx,
        )
        assert milestones == []

    def test_check_records_milestones(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        detector.check_milestones(
            user_id=1,
            segment_ctx=nt_ctx,
            achieved_goals=["Goal A"],
        )
        stored = detector.get_milestones(user_id=1)
        assert len(stored) == 1

    def test_check_milestones_segment_specific_habit(
        self, detector: MilestoneDetector, au_ctx: SegmentContext
    ) -> None:
        """AU user: 14 day streak triggers habit milestone."""
        milestones = detector.check_milestones(
            user_id=1,
            segment_ctx=au_ctx,
            habit_streaks={"reading": 14},
        )
        assert len(milestones) == 1
        assert milestones[0].milestone_type == MilestoneType.HABIT_ESTABLISHED

    def test_check_milestones_segment_specific_no_trigger(
        self, detector: MilestoneDetector, ad_ctx: SegmentContext
    ) -> None:
        """AD user: 14 day streak does NOT trigger habit milestone (needs 21)."""
        milestones = detector.check_milestones(
            user_id=1,
            segment_ctx=ad_ctx,
            habit_streaks={"reading": 14},
        )
        assert len(milestones) == 0


# ============================================================================
# GDPR tests
# ============================================================================


class TestMilestoneGDPR:
    def test_export(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        detector.check_milestones(
            user_id=1, segment_ctx=nt_ctx, achieved_goals=["Goal"]
        )
        data = detector.export_user_data(user_id=1)
        assert "milestones" in data
        assert len(data["milestones"]) == 1

    def test_delete(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        detector.check_milestones(
            user_id=1, segment_ctx=nt_ctx, achieved_goals=["Goal"]
        )
        detector.delete_user_data(user_id=1)
        data = detector.export_user_data(user_id=1)
        assert data["milestones"] == []

    def test_export_empty(self, detector: MilestoneDetector) -> None:
        data = detector.export_user_data(user_id=999)
        assert data["milestones"] == []

    def test_milestone_event_to_dict(
        self, detector: MilestoneDetector, nt_ctx: SegmentContext
    ) -> None:
        event = detector.detect_goal_achieved(
            user_id=1, segment_ctx=nt_ctx, goal_name="Test"
        )
        assert event is not None
        d = event.to_dict()
        assert d["milestone_type"] == "goal_achieved"
        assert d["user_id"] == 1
