"""
Tests for the Growth Tracker.

Covers:
- TrajectoryScore calculation and properties
- WindowComparison deltas and dimension detection
- GrowthSummary generation
- 3-window comparison (now/4w/12w)
- Segment-specific interoception adjustments
- Growth narrative generation
- GDPR export/delete
"""

from __future__ import annotations

import pytest

from src.agents.aurora.growth import (
    GrowthSummary,
    GrowthTracker,
    TrajectoryScore,
    WindowComparison,
)
from src.core.segment_context import SegmentContext


@pytest.fixture()
def tracker() -> GrowthTracker:
    """Create a GrowthTracker instance."""
    return GrowthTracker()


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
# TrajectoryScore tests
# ============================================================================


class TestTrajectoryScore:
    def test_default_score_is_zero(self) -> None:
        score = TrajectoryScore()
        assert score.overall == 0.0

    def test_overall_weighted_average(self) -> None:
        score = TrajectoryScore(
            consistency=1.0,
            resilience=1.0,
            self_awareness=1.0,
            goal_progress=1.0,
            wellbeing=1.0,
        )
        assert score.overall == 1.0

    def test_overall_partial_scores(self) -> None:
        score = TrajectoryScore(
            consistency=0.5,
            resilience=0.5,
            self_awareness=0.5,
            goal_progress=0.5,
            wellbeing=0.5,
        )
        assert score.overall == 0.5

    def test_to_dict(self) -> None:
        score = TrajectoryScore(consistency=0.8, resilience=0.6)
        d = score.to_dict()
        assert d["consistency"] == 0.8
        assert d["resilience"] == 0.6
        assert "overall" in d
        assert "timestamp" in d


# ============================================================================
# WindowComparison tests
# ============================================================================


class TestWindowComparison:
    def test_deltas_positive(self) -> None:
        current = TrajectoryScore(consistency=0.8, resilience=0.7)
        historical = TrajectoryScore(consistency=0.5, resilience=0.3)
        comp = WindowComparison(
            window_label="4_weeks", current=current, historical=historical
        )
        assert comp.delta_consistency == 0.3
        assert comp.delta_resilience == 0.4

    def test_deltas_negative(self) -> None:
        current = TrajectoryScore(consistency=0.3)
        historical = TrajectoryScore(consistency=0.8)
        comp = WindowComparison(
            window_label="4_weeks", current=current, historical=historical
        )
        assert comp.delta_consistency == -0.5

    def test_improving_dimensions(self) -> None:
        current = TrajectoryScore(
            consistency=0.8, resilience=0.7, self_awareness=0.5
        )
        historical = TrajectoryScore(
            consistency=0.2, resilience=0.1, self_awareness=0.5
        )
        comp = WindowComparison(
            window_label="4_weeks", current=current, historical=historical
        )
        improving = comp.improving_dimensions
        assert "consistency" in improving
        assert "resilience" in improving
        assert "self_awareness" not in improving

    def test_declining_dimensions(self) -> None:
        current = TrajectoryScore(wellbeing=0.2)
        historical = TrajectoryScore(wellbeing=0.8)
        comp = WindowComparison(
            window_label="12_weeks", current=current, historical=historical
        )
        declining = comp.declining_dimensions
        assert "wellbeing" in declining

    def test_to_dict(self) -> None:
        comp = WindowComparison(window_label="4_weeks")
        d = comp.to_dict()
        assert d["window_label"] == "4_weeks"
        assert "deltas" in d
        assert "improving" in d
        assert "declining" in d

    def test_delta_overall(self) -> None:
        current = TrajectoryScore(
            consistency=0.8, resilience=0.8,
            self_awareness=0.8, goal_progress=0.8, wellbeing=0.8,
        )
        historical = TrajectoryScore()
        comp = WindowComparison(
            window_label="4_weeks", current=current, historical=historical
        )
        assert comp.delta_overall > 0


# ============================================================================
# GrowthTracker tests
# ============================================================================


class TestGrowthTracker:
    def test_calculate_trajectory_basic(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        score = tracker.calculate_trajectory(
            user_id=1, segment_ctx=nt_ctx
        )
        assert 0.0 <= score.consistency <= 1.0
        assert 0.0 <= score.resilience <= 1.0
        assert 0.0 <= score.overall <= 1.0

    def test_calculate_trajectory_full_engagement(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=nt_ctx,
            engagement_days=7,
            total_days=7,
            setback_recovery_hours=0,
            energy_predictions_correct=5,
            energy_predictions_total=5,
            goals_completed=5,
            goals_total=5,
            avg_energy=1.0,
            avg_mood=1.0,
        )
        assert score.consistency == 1.0
        assert score.resilience == 1.0
        assert score.goal_progress == 1.0
        assert score.wellbeing == 1.0

    def test_calculate_trajectory_zero_engagement(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=nt_ctx,
            engagement_days=0,
            total_days=7,
            setback_recovery_hours=168,
            energy_predictions_correct=0,
            energy_predictions_total=5,
            goals_completed=0,
            goals_total=5,
            avg_energy=0.0,
            avg_mood=0.0,
        )
        assert score.consistency == 0.0
        assert score.resilience == 0.0
        assert score.goal_progress == 0.0
        assert score.wellbeing == 0.0

    def test_interoception_boost_audhd(
        self, tracker: GrowthTracker, ah_ctx: SegmentContext
    ) -> None:
        """AuDHD has very_low interoception, so moderate accuracy gets boosted."""
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=ah_ctx,
            energy_predictions_correct=3,
            energy_predictions_total=5,
        )
        # 0.6 * 1.5 = 0.9 (boosted due to very_low interoception)
        assert score.self_awareness == 0.9

    def test_interoception_boost_autism(
        self, tracker: GrowthTracker, au_ctx: SegmentContext
    ) -> None:
        """Autism has low interoception, moderate accuracy gets boosted."""
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=au_ctx,
            energy_predictions_correct=3,
            energy_predictions_total=5,
        )
        # 0.6 * 1.3 = 0.78
        assert score.self_awareness == 0.78

    def test_interoception_normal_adhd(
        self, tracker: GrowthTracker, ad_ctx: SegmentContext
    ) -> None:
        """ADHD has moderate interoception, no boost."""
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=ad_ctx,
            energy_predictions_correct=3,
            energy_predictions_total=5,
        )
        assert score.self_awareness == 0.6

    def test_interoception_normal_nt(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        """NT has high interoception, no boost."""
        score = tracker.calculate_trajectory(
            user_id=1,
            segment_ctx=nt_ctx,
            energy_predictions_correct=3,
            energy_predictions_total=5,
        )
        assert score.self_awareness == 0.6

    def test_compare_windows(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        current = TrajectoryScore(consistency=0.8, resilience=0.7)
        comp = tracker.compare_windows(user_id=1, current=current, weeks_ago=4)
        assert comp.window_label == "4_weeks"
        assert comp.current == current

    def test_get_growth_summary(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        summary = tracker.get_growth_summary(user_id=1, segment_ctx=nt_ctx)
        assert isinstance(summary, GrowthSummary)
        assert summary.user_id == 1
        assert summary.overall_trend in ("growing", "stable", "declining")
        assert summary.narrative != ""

    def test_growth_summary_with_existing_score(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        current = TrajectoryScore(
            consistency=0.9, resilience=0.8,
            self_awareness=0.7, goal_progress=0.6, wellbeing=0.8,
        )
        summary = tracker.get_growth_summary(
            user_id=1, segment_ctx=nt_ctx, current=current
        )
        assert summary.current == current

    def test_record_and_retrieve_scores(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        # Record multiple scores
        tracker.calculate_trajectory(user_id=1, segment_ctx=nt_ctx)
        tracker.calculate_trajectory(user_id=1, segment_ctx=nt_ctx)
        data = tracker.export_user_data(user_id=1)
        assert len(data["trajectory_scores"]) == 2

    def test_gdpr_export(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        tracker.calculate_trajectory(user_id=1, segment_ctx=nt_ctx)
        data = tracker.export_user_data(user_id=1)
        assert "trajectory_scores" in data
        assert len(data["trajectory_scores"]) == 1

    def test_gdpr_delete(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        tracker.calculate_trajectory(user_id=1, segment_ctx=nt_ctx)
        tracker.delete_user_data(user_id=1)
        data = tracker.export_user_data(user_id=1)
        assert data["trajectory_scores"] == []

    def test_narrative_growing(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        # Record a low historical score
        low = TrajectoryScore(
            consistency=0.1, resilience=0.1,
            self_awareness=0.1, goal_progress=0.1, wellbeing=0.1,
        )
        tracker.record_score(1, low)
        # Calculate a high current score
        current = TrajectoryScore(
            consistency=0.9, resilience=0.9,
            self_awareness=0.9, goal_progress=0.9, wellbeing=0.9,
        )
        summary = tracker.get_growth_summary(
            user_id=1, segment_ctx=nt_ctx, current=current
        )
        assert "upward" in summary.narrative.lower() or "improved" in summary.narrative.lower() or summary.overall_trend == "growing"

    def test_edge_case_zero_total_days(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        score = tracker.calculate_trajectory(
            user_id=1, segment_ctx=nt_ctx, total_days=0
        )
        assert score.consistency == 0.0

    def test_edge_case_zero_predictions(
        self, tracker: GrowthTracker, nt_ctx: SegmentContext
    ) -> None:
        score = tracker.calculate_trajectory(
            user_id=1, segment_ctx=nt_ctx,
            energy_predictions_correct=0,
            energy_predictions_total=0,
        )
        assert score.self_awareness == 0.5  # Default
