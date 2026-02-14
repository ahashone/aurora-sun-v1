"""
Comprehensive tests for the EffectivenessService (SW-6: Effectiveness Measurement Loop).

Tests cover:
- InterventionType enum
- InterventionOutcome enum
- SegmentCode enum (deprecated, maps to WorkingStyleCode)
- InterventionInstance model (delivery tracking)
- EffectivenessMetrics model (aggregated metrics)
- VariantExperiment model (A/B testing)
- EffectivenessService.log_intervention (records delivery)
- EffectivenessService.log_outcome (48h window outcome)
- EffectivenessService.get_effectiveness (query metrics)
- EffectivenessService.compare_variants (A/B test comparison, z-test)
- EffectivenessService.generate_weekly_report (admin report)
- EffectivenessService.get_pending_outcomes (interventions awaiting outcome)
- Success/failure categorization (SUCCESS_OUTCOMES, FAILURE_OUTCOMES)
- Latency calculation (delivery → outcome timing)
- Statistical significance (two-proportion z-test)
- Recommendation generation (low-performing segments/types)

Reference: ARCHITECTURE.md Section 2.6 (SW-6: Effectiveness Measurement Loop)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.effectiveness import (
    EffectivenessMetrics,
    EffectivenessReport,
    EffectivenessService,
    InterventionInstance,
    InterventionOutcome,
    InterventionOutcomeData,
    InterventionType,
    SegmentCode,
    get_effectiveness_service,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_metrics():
    """Create a mock EffectivenessMetrics with proper numeric defaults."""
    m = MagicMock(spec=EffectivenessMetrics)
    m.delivery_count = 0
    m.outcome_count = 0
    m.success_count = 0
    m.failure_count = 0
    m.no_response_count = 0
    m.total_latency_hours = 0.0
    m.avg_latency_hours = 0.0
    m.success_rate = 0.0
    m.failure_rate = 0.0
    m.no_response_rate = 0.0
    m.last_updated = None
    return m


@pytest.fixture
async def mock_session():
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    # Default execute returns a mock with scalar_one_or_none returning a proper metrics mock
    # This ensures _increment_delivery_count and _update_metrics find existing metrics
    default_result = MagicMock()
    default_result.scalar_one_or_none.return_value = _make_mock_metrics()
    default_result.scalars.return_value.all.return_value = []
    default_result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=default_result)
    return session


@pytest.fixture
async def service(mock_session):
    """Create an EffectivenessService with mock session."""
    return EffectivenessService(session=mock_session)


# =============================================================================
# Enum Tests
# =============================================================================


def test_intervention_type_enum():
    """Test InterventionType enum values."""
    assert InterventionType.INLINE_COACHING.value == "inline_coaching"
    assert InterventionType.BODY_DOUBLE.value == "body_double"
    assert InterventionType.PROACTIVE_IMPULSE.value == "proactive_impulse"
    assert InterventionType.CRISIS_CHECK.value == "crisis_check"


def test_intervention_outcome_enum():
    """Test InterventionOutcome enum values."""
    # Positive outcomes
    assert InterventionOutcome.TASK_COMPLETED.value == "task_completed"
    assert InterventionOutcome.ENERGY_IMPROVED.value == "energy_improved"

    # Negative outcomes
    assert InterventionOutcome.TASK_NOT_COMPLETED.value == "task_not_completed"
    assert InterventionOutcome.PATTERN_RECURRED.value == "pattern_recurred"

    # Neutral outcomes
    assert InterventionOutcome.NO_RESPONSE.value == "no_response"


def test_segment_code_enum():
    """Test SegmentCode enum (deprecated but exists)."""
    assert SegmentCode.AD.value == "AD"
    assert SegmentCode.AU.value == "AU"
    assert SegmentCode.AH.value == "AH"
    assert SegmentCode.NT.value == "NT"
    assert SegmentCode.CU.value == "CU"


# =============================================================================
# EffectivenessService.log_intervention Tests
# =============================================================================


@pytest.mark.asyncio
async def test_log_intervention_creates_instance(service, mock_session):
    """Test log_intervention creates InterventionInstance."""
    instance_id = await service.log_intervention(
        user_id=1,
        intervention_type="inline_coaching",
        intervention_id="coaching_001",
        segment="AD",
        module="aurora",
    )

    assert isinstance(instance_id, str)
    assert len(instance_id) == 36  # UUID format

    # Verify session.add was called
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_log_intervention_with_variant(service, mock_session):
    """Test log_intervention with A/B variant."""
    instance_id = await service.log_intervention(
        user_id=1,
        intervention_type="inline_coaching",
        intervention_id="coaching_001",
        segment="AD",
        module="aurora",
        variant="A",
    )

    assert isinstance(instance_id, str)


@pytest.mark.asyncio
async def test_log_intervention_increments_delivery_count(service, mock_session):
    """Test log_intervention increments delivery_count in metrics."""
    # Mock the query result to return None (no existing metrics)
    # When None is returned, a new EffectivenessMetrics is created.
    # But SQLAlchemy Column defaults aren't applied without DB,
    # so the new object has None for delivery_count.
    # Instead, test with an existing metrics mock to verify increment.
    existing_metrics = _make_mock_metrics()
    existing_metrics.delivery_count = 5

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_metrics
    mock_session.execute.return_value = mock_result

    await service.log_intervention(
        user_id=1,
        intervention_type="inline_coaching",
        intervention_id="coaching_001",
        segment="AD",
        module="aurora",
    )

    # Verify delivery_count was incremented
    assert existing_metrics.delivery_count == 6
    # Verify session.add was called once (for instance only, metrics already exists)
    assert mock_session.add.call_count == 1


# =============================================================================
# EffectivenessService.log_outcome Tests
# =============================================================================


@pytest.mark.asyncio
async def test_log_outcome_updates_instance(service, mock_session):
    """Test log_outcome updates intervention instance."""
    # Mock existing instance
    mock_instance = MagicMock(spec=InterventionInstance)
    mock_instance.delivered_at = datetime.now(UTC) - timedelta(hours=24)
    mock_instance.intervention_type = "inline_coaching"
    mock_instance.segment = "AD"
    mock_instance.user_id = 1

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_instance
    mock_session.execute.return_value = mock_result

    # Mock metrics query -- return a proper metrics mock
    mock_metrics_result = MagicMock()
    mock_metrics_result.scalar_one_or_none.return_value = _make_mock_metrics()
    mock_session.execute.side_effect = [mock_result, mock_metrics_result]

    await service.log_outcome(
        intervention_instance_id="test-uuid",
        outcome=InterventionOutcome.TASK_COMPLETED,
        user_id=1,
        system_verified=True,
    )

    # Verify commit was called
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_log_outcome_calculates_latency(service, mock_session):
    """Test log_outcome calculates latency correctly."""
    # Instance delivered 24 hours ago
    delivered_at = datetime.now(UTC) - timedelta(hours=24)
    mock_instance = MagicMock(spec=InterventionInstance)
    mock_instance.delivered_at = delivered_at
    mock_instance.intervention_type = "inline_coaching"
    mock_instance.segment = "AD"
    mock_instance.user_id = 1

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_instance
    mock_session.execute.return_value = mock_result

    # Mock metrics query -- return a proper metrics mock
    mock_metrics_result = MagicMock()
    mock_metrics_result.scalar_one_or_none.return_value = _make_mock_metrics()
    mock_session.execute.side_effect = [mock_result, mock_metrics_result]

    await service.log_outcome(
        intervention_instance_id="test-uuid",
        outcome=InterventionOutcome.TASK_COMPLETED,
        user_id=1,
        system_verified=True,
    )

    # Latency should be approximately 24 hours
    assert 23.0 <= mock_instance.outcome_latency_hours <= 25.0


@pytest.mark.asyncio
async def test_log_outcome_with_behavioral_signals(service, mock_session):
    """Test log_outcome with behavioral signals."""
    mock_instance = MagicMock(spec=InterventionInstance)
    mock_instance.delivered_at = datetime.now(UTC) - timedelta(hours=24)
    mock_instance.intervention_type = "inline_coaching"
    mock_instance.segment = "AD"
    mock_instance.user_id = 1

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_instance
    mock_session.execute.return_value = mock_result

    # Mock metrics query -- return a proper metrics mock
    mock_metrics_result = MagicMock()
    mock_metrics_result.scalar_one_or_none.return_value = _make_mock_metrics()
    mock_session.execute.side_effect = [mock_result, mock_metrics_result]

    signals = InterventionOutcomeData(
        outcome=InterventionOutcome.TASK_COMPLETED,
        task_completion_before=0.5,
        task_completion_after=0.8,
        energy_trajectory="improved",
    )

    # FINDING-025: user-reported outcomes (system_verified=False) have confidence
    # capped at MAX_USER_REPORTED_CONFIDENCE (0.9)
    await service.log_outcome(
        intervention_instance_id="test-uuid",
        outcome=InterventionOutcome.TASK_COMPLETED,
        behavioral_signals=signals,
        user_id=1,
        system_verified=False,
    )

    assert mock_instance.task_completion_before == 0.5
    # FINDING-025: 0.8 is below 0.9 cap, so it stays at 0.8
    assert mock_instance.task_completion_after == 0.8


@pytest.mark.asyncio
async def test_log_outcome_raises_on_not_found(service, mock_session):
    """Test log_outcome raises error when instance not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(ValueError, match="Intervention instance not found"):
        await service.log_outcome(
            intervention_instance_id="nonexistent-uuid",
            outcome=InterventionOutcome.TASK_COMPLETED,
            user_id=1,
        )


# =============================================================================
# EffectivenessService.get_effectiveness Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_effectiveness_empty_metrics(service, mock_session):
    """Test get_effectiveness with no metrics."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    metrics = await service.get_effectiveness()

    assert metrics.delivery_count == 0
    assert metrics.success_rate == 0.0


@pytest.mark.asyncio
async def test_get_effectiveness_with_filter(service, mock_session):
    """Test get_effectiveness with intervention_type filter."""
    mock_metrics = MagicMock(spec=EffectivenessMetrics)
    mock_metrics.delivery_count = 10
    mock_metrics.success_count = 7
    mock_metrics.failure_count = 2
    mock_metrics.no_response_count = 1
    mock_metrics.total_latency_hours = 120.0
    mock_metrics.outcome_count = 9

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_metrics]
    mock_session.execute.return_value = mock_result

    metrics = await service.get_effectiveness(intervention_type="inline_coaching")

    assert metrics.delivery_count == 10
    assert metrics.success_rate == 0.7


@pytest.mark.asyncio
async def test_get_effectiveness_aggregation(service, mock_session):
    """Test get_effectiveness aggregates multiple metrics."""
    mock_metrics_1 = MagicMock(spec=EffectivenessMetrics)
    mock_metrics_1.delivery_count = 10
    mock_metrics_1.success_count = 7
    mock_metrics_1.failure_count = 2
    mock_metrics_1.no_response_count = 1
    mock_metrics_1.total_latency_hours = 120.0
    mock_metrics_1.outcome_count = 9

    mock_metrics_2 = MagicMock(spec=EffectivenessMetrics)
    mock_metrics_2.delivery_count = 5
    mock_metrics_2.success_count = 3
    mock_metrics_2.failure_count = 1
    mock_metrics_2.no_response_count = 1
    mock_metrics_2.total_latency_hours = 60.0
    mock_metrics_2.outcome_count = 4

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_metrics_1, mock_metrics_2]
    mock_session.execute.return_value = mock_result

    metrics = await service.get_effectiveness()

    assert metrics.delivery_count == 15
    assert metrics.success_rate == 10 / 15


# =============================================================================
# EffectivenessService.compare_variants Tests
# =============================================================================


@pytest.mark.asyncio
async def test_compare_variants_insufficient_samples(service, mock_session):
    """Test compare_variants with insufficient samples."""
    # Mock counts: variant_a = 5, variant_b = 3 (both < min_samples=20)
    mock_session.execute.side_effect = [
        MagicMock(scalar=lambda: 3),  # success_a
        MagicMock(scalar=lambda: 5),  # total_a
        MagicMock(scalar=lambda: 2),  # success_b
        MagicMock(scalar=lambda: 3),  # total_b
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # no existing experiment
    ]

    result = await service.compare_variants(
        intervention_type="inline_coaching",
        variant_a="control",
        variant_b="treatment",
        segment="AD",
        min_samples=20,
    )

    assert result.variant_a_count == 5
    assert result.variant_b_count == 3
    assert result.winner is None
    assert result.is_significant is False


@pytest.mark.asyncio
async def test_compare_variants_with_significant_difference(service, mock_session):
    """Test compare_variants detects significant difference."""
    # Mock counts: variant_a = 50 success / 100 total, variant_b = 70 success / 100 total
    mock_session.execute.side_effect = [
        MagicMock(scalar=lambda: 50),   # success_a
        MagicMock(scalar=lambda: 100),  # total_a
        MagicMock(scalar=lambda: 70),   # success_b
        MagicMock(scalar=lambda: 100),  # total_b
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # no existing experiment
    ]

    result = await service.compare_variants(
        intervention_type="inline_coaching",
        variant_a="control",
        variant_b="treatment",
        segment="AD",
        min_samples=20,
    )

    assert result.variant_a_success_rate == 0.5
    assert result.variant_b_success_rate == 0.7
    # With large samples and 20% difference, should be significant
    assert result.is_significant is True
    assert result.winner == "treatment"


@pytest.mark.asyncio
async def test_compare_variants_no_difference(service, mock_session):
    """Test compare_variants with no significant difference."""
    # Mock counts: identical success rates
    mock_session.execute.side_effect = [
        MagicMock(scalar=lambda: 50),   # success_a
        MagicMock(scalar=lambda: 100),  # total_a
        MagicMock(scalar=lambda: 50),   # success_b
        MagicMock(scalar=lambda: 100),  # total_b
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # no existing experiment
    ]

    result = await service.compare_variants(
        intervention_type="inline_coaching",
        variant_a="control",
        variant_b="treatment",
        segment="AD",
        min_samples=20,
    )

    assert result.variant_a_success_rate == 0.5
    assert result.variant_b_success_rate == 0.5
    assert result.is_significant is False
    assert result.winner is None


# =============================================================================
# EffectivenessService.generate_weekly_report Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_weekly_report_structure(service, mock_session):
    """Test generate_weekly_report returns correct structure."""
    # Mock empty interventions
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [
        mock_result,  # interventions query
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # experiments query
    ]

    report = await service.generate_weekly_report()

    assert isinstance(report, EffectivenessReport)
    assert report.total_interventions == 0
    assert report.total_with_outcomes == 0
    assert isinstance(report.segment_stats, dict)
    assert isinstance(report.type_stats, dict)
    assert isinstance(report.top_performers, list)
    assert isinstance(report.recommendations, list)


@pytest.mark.asyncio
async def test_generate_weekly_report_with_interventions(service, mock_session):
    """Test generate_weekly_report with intervention data."""
    # Mock intervention instances
    mock_intervention_1 = MagicMock(spec=InterventionInstance)
    mock_intervention_1.segment = "AD"
    mock_intervention_1.intervention_type = "inline_coaching"
    mock_intervention_1.outcome = "task_completed"

    mock_intervention_2 = MagicMock(spec=InterventionInstance)
    mock_intervention_2.segment = "AD"
    mock_intervention_2.intervention_type = "inline_coaching"
    mock_intervention_2.outcome = "task_not_completed"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_intervention_1, mock_intervention_2]
    mock_session.execute.side_effect = [
        mock_result,
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # experiments
    ]

    report = await service.generate_weekly_report()

    assert report.total_interventions == 2
    assert report.total_with_outcomes == 2


@pytest.mark.asyncio
async def test_generate_weekly_report_recommendations(service, mock_session):
    """Test generate_weekly_report generates recommendations."""
    # Mock interventions with low success rate
    mock_interventions = []
    for _ in range(15):  # 15 deliveries, 3 successes (20% success rate)
        mock_int = MagicMock(spec=InterventionInstance)
        mock_int.segment = "AD"
        mock_int.intervention_type = "inline_coaching"
        mock_int.outcome = "task_not_completed"
        mock_interventions.append(mock_int)

    # Add 3 successes
    for _ in range(3):
        mock_int = MagicMock(spec=InterventionInstance)
        mock_int.segment = "AD"
        mock_int.intervention_type = "inline_coaching"
        mock_int.outcome = "task_completed"
        mock_interventions.append(mock_int)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_interventions
    mock_session.execute.side_effect = [
        mock_result,
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),
    ]

    report = await service.generate_weekly_report()

    # Should have recommendations for low success rate
    assert len(report.recommendations) > 0


# =============================================================================
# EffectivenessService.get_pending_outcomes Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_pending_outcomes_empty(service, mock_session):
    """Test get_pending_outcomes with no pending interventions."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    pending = await service.get_pending_outcomes()

    assert len(pending) == 0


@pytest.mark.asyncio
async def test_get_pending_outcomes_filters_by_age(service, mock_session):
    """Test get_pending_outcomes filters by max_age_hours."""
    mock_old_intervention = MagicMock(spec=InterventionInstance)
    mock_old_intervention.delivered_at = datetime.now(UTC) - timedelta(hours=50)
    mock_old_intervention.outcome = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_old_intervention]
    mock_session.execute.return_value = mock_result

    pending = await service.get_pending_outcomes(max_age_hours=48)

    # Should return the old intervention
    assert len(pending) == 1


# =============================================================================
# Success/Failure Categorization Tests
# =============================================================================


def test_success_outcomes_set():
    """Test SUCCESS_OUTCOMES contains positive outcomes."""
    assert InterventionOutcome.TASK_COMPLETED in EffectivenessService.SUCCESS_OUTCOMES
    assert InterventionOutcome.ENERGY_IMPROVED in EffectivenessService.SUCCESS_OUTCOMES
    assert InterventionOutcome.PATTERN_BROKEN in EffectivenessService.SUCCESS_OUTCOMES


def test_failure_outcomes_set():
    """Test FAILURE_OUTCOMES contains negative outcomes."""
    assert InterventionOutcome.TASK_NOT_COMPLETED in EffectivenessService.FAILURE_OUTCOMES
    assert InterventionOutcome.PATTERN_RECURRED in EffectivenessService.FAILURE_OUTCOMES
    assert InterventionOutcome.ENERGY_DECLINED in EffectivenessService.FAILURE_OUTCOMES


def test_success_and_failure_disjoint():
    """Test SUCCESS_OUTCOMES and FAILURE_OUTCOMES are disjoint."""
    assert len(EffectivenessService.SUCCESS_OUTCOMES & EffectivenessService.FAILURE_OUTCOMES) == 0


# =============================================================================
# Service Factory Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_effectiveness_service_factory(mock_session):
    """Test get_effectiveness_service factory function."""
    service = await get_effectiveness_service(mock_session)
    assert isinstance(service, EffectivenessService)
