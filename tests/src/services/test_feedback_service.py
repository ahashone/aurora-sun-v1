"""
Tests for Feedback Service.

Tests:
- Explicit feedback recording (thumbs up/down, ratings, comments)
- Implicit feedback integration (from EffectivenessService)
- Per-segment aggregation (NEVER across segments)
- Feedback summary and trends
- Weekly report generation
- GDPR methods (export, delete)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.feedback_service import (
    FeedbackContext,
    FeedbackService,
    FeedbackType,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Create async-compatible mock session for FeedbackService."""
    from src.services.feedback_service import FeedbackAggregation

    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()

    # Track objects added via session.add()
    added_objects: list = []

    def mock_add(obj):
        # Initialize FeedbackAggregation fields with defaults when added
        if isinstance(obj, FeedbackAggregation):
            if obj.total_feedback is None:
                obj.total_feedback = 0
            if obj.positive_count is None:
                obj.positive_count = 0
            if obj.negative_count is None:
                obj.negative_count = 0
            if obj.neutral_count is None:
                obj.neutral_count = 0
            if obj.total_ratings is None:
                obj.total_ratings = 0
            if obj.avg_rating is None:
                obj.avg_rating = 0.0
            if obj.sum_ratings is None:
                obj.sum_ratings = 0.0
            if obj.satisfaction_rate is None:
                obj.satisfaction_rate = 0.0
            if obj.dissatisfaction_rate is None:
                obj.dissatisfaction_rate = 0.0
        added_objects.append(obj)

    session.add = mock_add

    # Configure execute to return appropriate results
    async def mock_execute(stmt):
        # Check query type
        stmt_str = str(stmt)
        mock_result = MagicMock()

        # Get bound parameters if available
        params = {}
        if hasattr(stmt, 'compile'):
            compiled = stmt.compile(compile_kwargs={"literal_binds": False})
            params = compiled.params if hasattr(compiled, 'params') else {}

        # Debug
        # print(f"QUERY params: {params}")

        # Handle COUNT queries - return integer
        if "count(" in stmt_str.lower() or "func.count" in stmt_str:
            mock_result.scalar.return_value = 0
            mock_result.scalar_one_or_none.return_value = 0
            return mock_result

        # Handle FeedbackAggregation queries
        if "feedback_aggregation" in stmt_str.lower():
            # Extract filters from params
            segment_filter = params.get('segment_1')
            context_type_filter = params.get('context_type_1')
            context_id_filter = params.get('context_id_1')

            # Return matching FeedbackAggregation objects
            agg_objects = [obj for obj in added_objects if isinstance(obj, FeedbackAggregation)]

            # Apply filters
            if segment_filter:
                agg_objects = [obj for obj in agg_objects if obj.segment == segment_filter]
            if context_type_filter:
                agg_objects = [obj for obj in agg_objects if obj.context_type == context_type_filter]
            if context_id_filter is not None:
                agg_objects = [obj for obj in agg_objects if obj.context_id == context_id_filter]

            if agg_objects:
                mock_result.scalar_one_or_none.return_value = agg_objects[-1]
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = agg_objects
                mock_result.scalars.return_value = mock_scalars
            else:
                # No aggregation exists yet - will be created
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
        else:
            # Default empty result
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar.return_value = 0

        return mock_result

    session.execute = mock_execute

    return session


@pytest.fixture
def feedback_service(mock_session: MagicMock) -> FeedbackService:  # type: ignore[no-untyped-def]
    """Create FeedbackService instance with mock async session."""
    return FeedbackService(session=mock_session)  # type: ignore[arg-type]


# =============================================================================
# Explicit Feedback Recording
# =============================================================================


@pytest.mark.asyncio
async def test_record_thumbs_up(feedback_service: FeedbackService) -> None:
    """Test recording thumbs up feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=1,
        segment="AD",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.INTERVENTION,
        context_id="inline_coaching_123",
        module="planning",
        is_explicit=True,
    )

    assert feedback_id is not None
    assert isinstance(feedback_id, str)
    assert len(feedback_id) > 0


@pytest.mark.asyncio
async def test_record_thumbs_down(feedback_service: FeedbackService) -> None:
    """Test recording thumbs down feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=1,
        segment="AU",
        feedback_type=FeedbackType.THUMBS_DOWN,
        context_type=FeedbackContext.COACHING,
        context_id="coaching_456",
        is_explicit=True,
    )

    assert feedback_id is not None


@pytest.mark.asyncio
async def test_record_rating(feedback_service: FeedbackService) -> None:
    """Test recording rating feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=2,
        segment="AH",
        feedback_type=FeedbackType.RATING,
        context_type=FeedbackContext.MODULE,
        context_id="habit",
        module="habit",
        feedback_value=4.5,
        is_explicit=True,
    )

    assert feedback_id is not None


@pytest.mark.asyncio
async def test_record_comment(feedback_service: FeedbackService) -> None:
    """Test recording comment feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=3,
        segment="NT",
        feedback_type=FeedbackType.COMMENT,
        context_type=FeedbackContext.DAILY_WORKFLOW,
        context_id="morning_activation",
        feedback_comment="This was very helpful for my morning routine",
        is_explicit=True,
    )

    assert feedback_id is not None


# =============================================================================
# Implicit Feedback Recording
# =============================================================================


@pytest.mark.asyncio
async def test_record_implicit_task_completed(feedback_service: FeedbackService) -> None:
    """Test recording implicit task completion feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=1,
        segment="AD",
        feedback_type=FeedbackType.TASK_COMPLETED,
        context_type=FeedbackContext.INTERVENTION,
        context_id="pinch_activation",
        intervention_type="inline_coaching",
        is_explicit=False,
    )

    assert feedback_id is not None


@pytest.mark.asyncio
async def test_record_implicit_pattern_broken(feedback_service: FeedbackService) -> None:
    """Test recording implicit pattern broken feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=2,
        segment="AU",
        feedback_type=FeedbackType.PATTERN_BROKEN,
        context_type=FeedbackContext.COACHING,
        context_id="burnout_redirect",
        is_explicit=False,
    )

    assert feedback_id is not None


@pytest.mark.asyncio
async def test_record_implicit_energy_improved(feedback_service: FeedbackService) -> None:
    """Test recording implicit energy improvement feedback."""
    feedback_id = await feedback_service.record_feedback(
        user_id=3,
        segment="AH",
        feedback_type=FeedbackType.ENERGY_IMPROVED,
        context_type=FeedbackContext.DAILY_WORKFLOW,
        context_id="energy_check",
        is_explicit=False,
    )

    assert feedback_id is not None


# =============================================================================
# Aggregation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_aggregation_counts_positive(feedback_service: FeedbackService) -> None:
    """Test aggregation counts positive feedback correctly."""
    # Record multiple positive feedback items
    for i in range(5):
        await feedback_service.record_feedback(
            user_id=i + 1,
            segment="AD",
            feedback_type=FeedbackType.THUMBS_UP,
            context_type=FeedbackContext.INTERVENTION,
            context_id="test_intervention",
            is_explicit=True,
        )

    # Get summary
    summaries = await feedback_service.get_summary(
        segment="AD",
        context_type=FeedbackContext.INTERVENTION,
        context_id="test_intervention",
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.positive_count == 5
    assert summary.satisfaction_rate == 1.0  # 100% positive


@pytest.mark.asyncio
async def test_aggregation_counts_negative(feedback_service: FeedbackService) -> None:
    """Test aggregation counts negative feedback correctly."""
    # Record multiple negative feedback items
    for i in range(3):
        await feedback_service.record_feedback(
            user_id=i + 1,
            segment="AU",
            feedback_type=FeedbackType.THUMBS_DOWN,
            context_type=FeedbackContext.MODULE,
            context_id="test_module",
            is_explicit=True,
        )

    # Get summary
    summaries = await feedback_service.get_summary(
        segment="AU",
        context_type=FeedbackContext.MODULE,
        context_id="test_module",
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.negative_count == 3
    assert summary.satisfaction_rate == 0.0  # 0% positive (100% negative)


@pytest.mark.asyncio
async def test_aggregation_mixed_feedback(feedback_service: FeedbackService) -> None:
    """Test aggregation with mixed feedback."""
    # Record 7 positive, 3 negative
    for i in range(7):
        await feedback_service.record_feedback(
            user_id=i + 1,
            segment="AH",
            feedback_type=FeedbackType.THUMBS_UP,
            context_type=FeedbackContext.COACHING,
            context_id="mixed_test",
            is_explicit=True,
        )

    for i in range(3):
        await feedback_service.record_feedback(
            user_id=i + 10,
            segment="AH",
            feedback_type=FeedbackType.THUMBS_DOWN,
            context_type=FeedbackContext.COACHING,
            context_id="mixed_test",
            is_explicit=True,
        )

    # Get summary
    summaries = await feedback_service.get_summary(
        segment="AH",
        context_type=FeedbackContext.COACHING,
        context_id="mixed_test",
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.total_feedback == 10
    assert summary.positive_count == 7
    assert summary.negative_count == 3
    assert abs(summary.satisfaction_rate - 0.7) < 0.01  # 70% positive


@pytest.mark.asyncio
async def test_aggregation_per_segment_isolation(feedback_service: FeedbackService) -> None:
    """Test that aggregation is per-segment (never across segments)."""
    # Record feedback for AD segment
    await feedback_service.record_feedback(
        user_id=1,
        segment="AD",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.INTERVENTION,
        context_id="shared_context",
        is_explicit=True,
    )

    # Record feedback for AU segment
    await feedback_service.record_feedback(
        user_id=2,
        segment="AU",
        feedback_type=FeedbackType.THUMBS_DOWN,
        context_type=FeedbackContext.INTERVENTION,
        context_id="shared_context",
        is_explicit=True,
    )

    # Get summary for AD
    summaries_ad = await feedback_service.get_summary(
        segment="AD",
        context_type=FeedbackContext.INTERVENTION,
        context_id="shared_context",
    )

    # Get summary for AU
    summaries_au = await feedback_service.get_summary(
        segment="AU",
        context_type=FeedbackContext.INTERVENTION,
        context_id="shared_context",
    )

    # Each segment should have separate aggregation
    assert len(summaries_ad) == 1
    assert len(summaries_au) == 1

    # AD should have 1 positive
    assert summaries_ad[0].positive_count == 1
    assert summaries_ad[0].negative_count == 0

    # AU should have 1 negative
    assert summaries_au[0].positive_count == 0
    assert summaries_au[0].negative_count == 1


# =============================================================================
# Rating Aggregation
# =============================================================================


@pytest.mark.asyncio
async def test_rating_aggregation(feedback_service: FeedbackService) -> None:
    """Test rating aggregation calculates average correctly."""
    # Record ratings: 5, 4, 3, 5, 4 (average = 4.2)
    ratings = [5.0, 4.0, 3.0, 5.0, 4.0]
    for i, rating in enumerate(ratings):
        await feedback_service.record_feedback(
            user_id=i + 1,
            segment="NT",
            feedback_type=FeedbackType.RATING,
            context_type=FeedbackContext.MODULE,
            context_id="rating_test",
            feedback_value=rating,
            is_explicit=True,
        )

    # Get summary
    summaries = await feedback_service.get_summary(
        segment="NT",
        context_type=FeedbackContext.MODULE,
        context_id="rating_test",
    )

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.avg_rating is not None
    assert abs(summary.avg_rating - 4.2) < 0.01


# =============================================================================
# Trend Analysis
# =============================================================================


@pytest.mark.asyncio
async def test_get_trend_improving(feedback_service: FeedbackService) -> None:
    """Test trend detection for improving satisfaction."""
    # This would require time-manipulation to test properly
    # For now, we'll just test that the method runs without error
    trend = await feedback_service.get_trend(
        segment="AD",
        context_type=FeedbackContext.INTERVENTION,
        context_id="trend_test",
        time_window_days=7,
    )

    assert trend is not None
    assert trend.trend_direction in ["improving", "stable", "declining"]


# =============================================================================
# Weekly Report
# =============================================================================


@pytest.mark.asyncio
async def test_generate_weekly_report(feedback_service: FeedbackService) -> None:
    """Test weekly report generation."""
    # Record some feedback
    await feedback_service.record_feedback(
        user_id=1,
        segment="AD",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.INTERVENTION,
        context_id="report_test",
        is_explicit=True,
    )

    # Generate report
    report = await feedback_service.generate_weekly_report()

    assert report is not None
    assert report.total_feedback >= 0
    assert isinstance(report.segment_stats, dict)
    assert isinstance(report.top_performing, list)
    assert isinstance(report.underperforming, list)
    assert isinstance(report.recommendations, list)


@pytest.mark.asyncio
async def test_weekly_report_recommendations(feedback_service: FeedbackService) -> None:
    """Test weekly report includes recommendations for low satisfaction."""
    # Record low satisfaction feedback (20% positive)
    for i in range(8):
        await feedback_service.record_feedback(
            user_id=i + 1,
            segment="AU",
            feedback_type=FeedbackType.THUMBS_DOWN,
            context_type=FeedbackContext.MODULE,
            context_id="low_satisfaction",
            is_explicit=True,
        )

    for i in range(2):
        await feedback_service.record_feedback(
            user_id=i + 10,
            segment="AU",
            feedback_type=FeedbackType.THUMBS_UP,
            context_type=FeedbackContext.MODULE,
            context_id="low_satisfaction",
            is_explicit=True,
        )

    # Generate report
    report = await feedback_service.generate_weekly_report()

    # Should have recommendations for low satisfaction
    assert len(report.recommendations) > 0


# =============================================================================
# GDPR Methods
# =============================================================================


@pytest.mark.asyncio
async def test_export_user_feedback(feedback_service: FeedbackService) -> None:
    """Test GDPR export for a user."""
    # Record some feedback
    await feedback_service.record_feedback(
        user_id=100,
        segment="AD",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.INTERVENTION,
        context_id="export_test",
        is_explicit=True,
    )

    # Export
    data = await feedback_service.export_user_feedback(user_id=100)

    assert isinstance(data, dict)
    assert "feedback_records" in data
    assert isinstance(data["feedback_records"], list)


@pytest.mark.asyncio
async def test_delete_user_feedback(feedback_service: FeedbackService) -> None:
    """Test GDPR delete for a user."""
    # Record feedback
    await feedback_service.record_feedback(
        user_id=200,
        segment="AU",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.MODULE,
        context_id="delete_test",
        is_explicit=True,
    )

    # Delete
    await feedback_service.delete_user_feedback(user_id=200)

    # Export should be empty
    data = await feedback_service.export_user_feedback(user_id=200)
    assert len(data["feedback_records"]) == 0


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_get_summary_empty_filters(feedback_service: FeedbackService) -> None:
    """Test get_summary with no filters returns all aggregations."""
    summaries = await feedback_service.get_summary()

    # Should return all aggregations (may be empty if no feedback yet)
    assert isinstance(summaries, list)


@pytest.mark.asyncio
async def test_record_feedback_without_optional_fields(feedback_service: FeedbackService) -> None:
    """Test recording feedback with minimal required fields."""
    feedback_id = await feedback_service.record_feedback(
        user_id=1,
        segment="AD",
        feedback_type=FeedbackType.THUMBS_UP,
        context_type=FeedbackContext.INTERVENTION,
        is_explicit=True,
    )

    assert feedback_id is not None


@pytest.mark.asyncio
async def test_aggregation_handles_zero_feedback(feedback_service: FeedbackService) -> None:
    """Test aggregation handles zero feedback gracefully."""
    summaries = await feedback_service.get_summary(
        segment="CU",
        context_type=FeedbackContext.MODULE,
        context_id="nonexistent",
    )

    # Should return empty list or zero counts
    assert isinstance(summaries, list)
