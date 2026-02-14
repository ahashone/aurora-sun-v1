"""
Comprehensive tests for the PatternDetectionService (5 Destructive Cycles + 14 Daily Burden Signals).

Tests cover:
- CycleType enum (5 core cycles)
- CycleSeverity enum (NONE, EMERGING, ACTIVE, SEVERE)
- DetectedCycle dataclass
- Intervention dataclass and INTERVENTIONS dict
- SignalName enum (14 Daily Burden signals)
- SIGNAL_METADATA (applicable_segments, research_source)
- SIGNAL_THRESHOLDS (severity thresholds per signal)
- PatternDetectionService.detect_cycles (all 5 cycles from recent_data)
- PatternDetectionService.get_intervention (segment-specific interventions)
- PatternDetectionService.detect_signal (signal intensity 0-1)
- PatternDetectionService.get_signal_severity (threshold-based severity)
- PatternDetectionService.get_signals_for_segment (filter by applicable_segments)
- PatternDetectionService.get_cycle_summary (active cycles for user)
- Singleton access (get_pattern_detection_service)
- Segment-specific interventions (different approaches for AD/AU/AH)
- Detection accuracy (cycles detected when evidence present)

Reference: knowledge/research/meta-syntheses/meta-synthesis-daily-burden-*.json
"""

from __future__ import annotations

import pytest

from src.core.segment_context import SegmentContext
from src.services.pattern_detection import (
    INTERVENTIONS,
    SIGNAL_METADATA,
    SIGNAL_THRESHOLDS,
    CycleSeverity,
    CycleType,
    DetectedCycle,
    Intervention,
    PatternDetectionService,
    SignalName,
    get_pattern_detection_service,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service():
    """Create a fresh PatternDetectionService instance."""
    return PatternDetectionService()


@pytest.fixture
def adhd_context():
    """ADHD segment context."""
    return SegmentContext.from_code("AD")


@pytest.fixture
def autism_context():
    """Autism segment context."""
    return SegmentContext.from_code("AU")


@pytest.fixture
def audhd_context():
    """AuDHD segment context."""
    return SegmentContext.from_code("AH")


@pytest.fixture
def nt_context():
    """Neurotypical segment context."""
    return SegmentContext.from_code("NT")


@pytest.fixture
def meta_spirale_data():
    """Recent data showing meta-spirale pattern."""
    return {
        "task_completion_rate": 0.4,
        "new_starts_count": 2,
        "abandoned_tasks_count": 1,
        "social_interactions_count": 3,
        "unpaid_work_hours": 5.0,
        "overthinking_indicators": ["paralyzed by decision", "thinking about thinking", "recursive loop"],
        "perfectionism_evidence": [],
        "isolation_evidence": [],
    }


@pytest.fixture
def shiny_object_data():
    """Recent data showing shiny object syndrome."""
    return {
        "task_completion_rate": 0.2,
        "new_starts_count": 10,
        "abandoned_tasks_count": 8,
        "social_interactions_count": 5,
        "unpaid_work_hours": 3.0,
        "overthinking_indicators": [],
        "perfectionism_evidence": [],
        "isolation_evidence": [],
    }


@pytest.fixture
def perfectionism_data():
    """Recent data showing perfectionism pattern."""
    return {
        "task_completion_rate": 0.3,
        "new_starts_count": 3,
        "abandoned_tasks_count": 4,
        "social_interactions_count": 4,
        "unpaid_work_hours": 2.0,
        "overthinking_indicators": [],
        "perfectionism_evidence": ["never good enough", "endless refinement", "fear of judgment"],
        "isolation_evidence": [],
    }


@pytest.fixture
def isolation_data():
    """Recent data showing isolation pattern."""
    return {
        "task_completion_rate": 0.5,
        "new_starts_count": 2,
        "abandoned_tasks_count": 1,
        "social_interactions_count": 1,
        "unpaid_work_hours": 1.0,
        "overthinking_indicators": [],
        "perfectionism_evidence": [],
        "isolation_evidence": ["avoiding friends", "no energy for people", "withdrawing"],
    }


@pytest.fixture
def free_work_data():
    """Recent data showing free work pattern."""
    return {
        "task_completion_rate": 0.6,
        "new_starts_count": 4,
        "abandoned_tasks_count": 2,
        "social_interactions_count": 6,
        "unpaid_work_hours": 25.0,
        "overthinking_indicators": [],
        "perfectionism_evidence": [],
        "isolation_evidence": [],
    }


# =============================================================================
# Enum Tests
# =============================================================================


def test_cycle_type_enum():
    """Test CycleType enum values."""
    assert CycleType.META_SPIRALE.value == "meta_spirale"
    assert CycleType.SHINY_OBJECT.value == "shiny_object"
    assert CycleType.PERFECTIONISM.value == "perfectionism"
    assert CycleType.ISOLATION.value == "isolation"
    assert CycleType.FREE_WORK.value == "free_work"


def test_cycle_severity_enum():
    """Test CycleSeverity enum values."""
    assert CycleSeverity.NONE.value == "none"
    assert CycleSeverity.EMERGING.value == "emerging"
    assert CycleSeverity.ACTIVE.value == "active"
    assert CycleSeverity.SEVERE.value == "severe"


def test_signal_name_enum():
    """Test SignalName enum has all 14+ signals."""
    # AD signals
    assert SignalName.MASKING_ESCALATION
    assert SignalName.TIME_BLINDNESS_SEVERITY
    assert SignalName.RSD_ESCALATION

    # AU signals
    assert SignalName.ENERGY_DEPLETION_RATE
    assert SignalName.INERTIA_FREQUENCY
    assert SignalName.CAPACITY_DECLINE_TREND

    # AH signals
    assert SignalName.DOUBLE_MASKING_COST
    assert SignalName.CHANNEL_DOMINANCE_SHIFTS


# =============================================================================
# Signal Metadata Tests
# =============================================================================


def test_signal_metadata_complete():
    """Test SIGNAL_METADATA contains all signals."""
    assert len(SIGNAL_METADATA) >= 14
    for signal in SignalName:
        assert signal in SIGNAL_METADATA


def test_signal_metadata_structure():
    """Test SIGNAL_METADATA structure."""
    for signal, metadata in SIGNAL_METADATA.items():
        assert "segment" in metadata
        assert "applicable_segments" in metadata
        assert "category" in metadata
        assert "description" in metadata
        assert isinstance(metadata["applicable_segments"], list)


def test_signal_metadata_applicable_segments():
    """Test applicable_segments field."""
    # ADHD signals should include AD and sometimes AH
    masking_escalation = SIGNAL_METADATA[SignalName.MASKING_ESCALATION]
    assert "AD" in masking_escalation["applicable_segments"]

    # Autism signals should include AU and sometimes AH
    inertia_freq = SIGNAL_METADATA[SignalName.INERTIA_FREQUENCY]
    assert "AU" in inertia_freq["applicable_segments"]

    # AuDHD-specific signals should only include AH
    double_masking = SIGNAL_METADATA[SignalName.DOUBLE_MASKING_COST]
    assert double_masking["applicable_segments"] == ["AH"]


def test_signal_thresholds_complete():
    """Test SIGNAL_THRESHOLDS contains all signals."""
    for signal in SignalName:
        assert signal in SIGNAL_THRESHOLDS


def test_signal_thresholds_structure():
    """Test SIGNAL_THRESHOLDS structure (tuple of two floats)."""
    for signal, thresholds in SIGNAL_THRESHOLDS.items():
        assert isinstance(thresholds, tuple)
        assert len(thresholds) == 2
        assert thresholds[0] < thresholds[1]  # emerging < severe


# =============================================================================
# Intervention Tests
# =============================================================================


def test_interventions_all_cycles_covered():
    """Test INTERVENTIONS covers all 5 cycle types."""
    assert CycleType.META_SPIRALE in INTERVENTIONS
    assert CycleType.SHINY_OBJECT in INTERVENTIONS
    assert CycleType.PERFECTIONISM in INTERVENTIONS
    assert CycleType.ISOLATION in INTERVENTIONS
    assert CycleType.FREE_WORK in INTERVENTIONS


def test_interventions_all_segments_per_cycle():
    """Test each cycle has interventions for AD/AU/AH."""
    for cycle_type in CycleType:
        segment_interventions = INTERVENTIONS[cycle_type]
        assert "AD" in segment_interventions
        assert "AU" in segment_interventions
        assert "AH" in segment_interventions


def test_intervention_structure():
    """Test Intervention dataclass structure."""
    intervention = INTERVENTIONS[CycleType.META_SPIRALE]["AD"]
    assert isinstance(intervention, Intervention)
    assert intervention.cycle_type == CycleType.META_SPIRALE
    assert intervention.segment == "AD"
    assert isinstance(intervention.title, str)
    assert isinstance(intervention.description, str)
    assert isinstance(intervention.resources, list)


# =============================================================================
# PatternDetectionService.detect_cycles Tests
# =============================================================================


@pytest.mark.asyncio
async def test_detect_cycles_returns_all_five(service):
    """Test detect_cycles always returns all 5 cycles."""
    cycles = await service.detect_cycles(user_id=1, recent_data={})
    assert len(cycles) == 5

    cycle_types = {c.cycle_type for c in cycles}
    assert cycle_types == {
        CycleType.META_SPIRALE,
        CycleType.SHINY_OBJECT,
        CycleType.PERFECTIONISM,
        CycleType.ISOLATION,
        CycleType.FREE_WORK,
    }


@pytest.mark.asyncio
async def test_detect_cycles_meta_spirale_detection(service, meta_spirale_data):
    """Test detection of meta-spirale cycle."""
    cycles = await service.detect_cycles(user_id=1, recent_data=meta_spirale_data)

    meta_spirale = next(c for c in cycles if c.cycle_type == CycleType.META_SPIRALE)
    assert meta_spirale.severity in [CycleSeverity.EMERGING, CycleSeverity.SEVERE]
    assert len(meta_spirale.evidence) > 0


@pytest.mark.asyncio
async def test_detect_cycles_shiny_object_detection(service, shiny_object_data):
    """Test detection of shiny object syndrome."""
    cycles = await service.detect_cycles(user_id=1, recent_data=shiny_object_data)

    shiny_object = next(c for c in cycles if c.cycle_type == CycleType.SHINY_OBJECT)
    assert shiny_object.severity in [CycleSeverity.EMERGING, CycleSeverity.ACTIVE, CycleSeverity.SEVERE]
    assert shiny_object.confidence > 0.0


@pytest.mark.asyncio
async def test_detect_cycles_perfectionism_detection(service, perfectionism_data):
    """Test detection of perfectionism cycle."""
    cycles = await service.detect_cycles(user_id=1, recent_data=perfectionism_data)

    perfectionism = next(c for c in cycles if c.cycle_type == CycleType.PERFECTIONISM)
    assert perfectionism.severity in [CycleSeverity.EMERGING, CycleSeverity.SEVERE]


@pytest.mark.asyncio
async def test_detect_cycles_isolation_detection(service, isolation_data):
    """Test detection of isolation cycle."""
    cycles = await service.detect_cycles(user_id=1, recent_data=isolation_data)

    isolation = next(c for c in cycles if c.cycle_type == CycleType.ISOLATION)
    assert isolation.severity in [CycleSeverity.EMERGING, CycleSeverity.ACTIVE, CycleSeverity.SEVERE]


@pytest.mark.asyncio
async def test_detect_cycles_free_work_detection(service, free_work_data):
    """Test detection of free work cycle."""
    cycles = await service.detect_cycles(user_id=1, recent_data=free_work_data)

    free_work = next(c for c in cycles if c.cycle_type == CycleType.FREE_WORK)
    assert free_work.severity in [CycleSeverity.ACTIVE, CycleSeverity.SEVERE]


@pytest.mark.asyncio
async def test_detect_cycles_severity_thresholds(service):
    """Test cycle severity thresholds."""
    # Severe shiny object: high abandonment ratio
    # abandonment_ratio = abandoned / (new_starts + abandoned) > 0.7
    severe_data = {
        "new_starts_count": 3,
        "abandoned_tasks_count": 10,
    }
    cycles = await service.detect_cycles(user_id=1, recent_data=severe_data)
    shiny = next(c for c in cycles if c.cycle_type == CycleType.SHINY_OBJECT)
    assert shiny.severity == CycleSeverity.SEVERE


@pytest.mark.asyncio
async def test_detect_cycles_stores_history(service):
    """Test detect_cycles stores history in _cycle_history."""
    await service.detect_cycles(user_id=42, recent_data={})
    assert 42 in service._cycle_history
    assert len(service._cycle_history[42]) == 5


# =============================================================================
# PatternDetectionService.get_intervention Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_intervention_adhd(service, adhd_context):
    """Test get_intervention for ADHD segment."""
    cycle = DetectedCycle(
        cycle_type=CycleType.META_SPIRALE,
        severity=CycleSeverity.ACTIVE,
        confidence=0.8,
    )
    intervention = await service.get_intervention(cycle, adhd_context)

    assert intervention is not None
    assert intervention.segment == "AD"
    assert intervention.cycle_type == CycleType.META_SPIRALE


@pytest.mark.asyncio
async def test_get_intervention_autism(service, autism_context):
    """Test get_intervention for Autism segment."""
    cycle = DetectedCycle(
        cycle_type=CycleType.PERFECTIONISM,
        severity=CycleSeverity.SEVERE,
        confidence=0.9,
    )
    intervention = await service.get_intervention(cycle, autism_context)

    assert intervention is not None
    assert intervention.segment == "AU"


@pytest.mark.asyncio
async def test_get_intervention_audhd(service, audhd_context):
    """Test get_intervention for AuDHD segment."""
    cycle = DetectedCycle(
        cycle_type=CycleType.ISOLATION,
        severity=CycleSeverity.ACTIVE,
        confidence=0.75,
    )
    intervention = await service.get_intervention(cycle, audhd_context)

    assert intervention is not None
    assert intervention.segment == "AH"


@pytest.mark.asyncio
async def test_get_intervention_none_for_none_severity(service, adhd_context):
    """Test get_intervention returns None for NONE severity."""
    cycle = DetectedCycle(
        cycle_type=CycleType.META_SPIRALE,
        severity=CycleSeverity.NONE,
        confidence=0.0,
    )
    intervention = await service.get_intervention(cycle, adhd_context)
    assert intervention is None


@pytest.mark.asyncio
async def test_get_intervention_different_approaches_per_segment(service, adhd_context, autism_context):
    """Test different segments get different intervention approaches."""
    cycle = DetectedCycle(
        cycle_type=CycleType.SHINY_OBJECT,
        severity=CycleSeverity.ACTIVE,
        confidence=0.8,
    )

    adhd_intervention = await service.get_intervention(cycle, adhd_context)
    autism_intervention = await service.get_intervention(cycle, autism_context)

    # Different approaches for same cycle
    assert adhd_intervention.title != autism_intervention.title
    assert adhd_intervention.description != autism_intervention.description


# =============================================================================
# PatternDetectionService.detect_signal Tests
# =============================================================================


@pytest.mark.asyncio
async def test_detect_signal_returns_score(service):
    """Test detect_signal returns float 0.0-1.0."""
    score = await service.detect_signal(user_id=1, signal_name=SignalName.MASKING_ESCALATION)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
async def test_detect_signal_initializes_history(service):
    """Test detect_signal initializes history."""
    await service.detect_signal(user_id=42, signal_name=SignalName.RSD_ESCALATION)
    assert 42 in service._signal_history
    assert SignalName.RSD_ESCALATION in service._signal_history[42]


@pytest.mark.asyncio
async def test_detect_signal_invalid_signal_returns_zero(service):
    """Test detect_signal with invalid signal name returns 0.0."""
    # Create a mock signal that's not in metadata
    class FakeSignal:
        pass

    fake_signal = FakeSignal()
    score = await service.detect_signal(user_id=1, signal_name=fake_signal)  # type: ignore
    assert score == 0.0


# =============================================================================
# PatternDetectionService.get_signal_severity Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_signal_severity_none(service):
    """Test get_signal_severity returns NONE for 0.0."""
    severity = await service.get_signal_severity(SignalName.MASKING_ESCALATION, 0.0)
    assert severity == CycleSeverity.NONE


@pytest.mark.asyncio
async def test_get_signal_severity_emerging(service):
    """Test get_signal_severity returns EMERGING for low score."""
    severity = await service.get_signal_severity(SignalName.MASKING_ESCALATION, 0.2)
    assert severity == CycleSeverity.EMERGING


@pytest.mark.asyncio
async def test_get_signal_severity_active(service):
    """Test get_signal_severity returns ACTIVE for medium score."""
    severity = await service.get_signal_severity(SignalName.MASKING_ESCALATION, 0.5)
    assert severity == CycleSeverity.ACTIVE


@pytest.mark.asyncio
async def test_get_signal_severity_severe(service):
    """Test get_signal_severity returns SEVERE for high score."""
    severity = await service.get_signal_severity(SignalName.MASKING_ESCALATION, 0.9)
    assert severity == CycleSeverity.SEVERE


@pytest.mark.asyncio
async def test_get_signal_severity_respects_thresholds(service):
    """Test get_signal_severity uses signal-specific thresholds."""
    # Different signals have different thresholds
    for signal, (emerging_threshold, severe_threshold) in SIGNAL_THRESHOLDS.items():
        # Just below emerging threshold → EMERGING
        severity_low = await service.get_signal_severity(signal, emerging_threshold + 0.01)
        assert severity_low in [CycleSeverity.EMERGING, CycleSeverity.ACTIVE]

        # At severe threshold → SEVERE
        severity_high = await service.get_signal_severity(signal, severe_threshold)
        assert severity_high == CycleSeverity.SEVERE


# =============================================================================
# PatternDetectionService.get_signals_for_segment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_signals_for_segment_adhd(service, adhd_context):
    """Test get_signals_for_segment for ADHD."""
    signals = await service.get_signals_for_segment(adhd_context)

    assert len(signals) > 0
    # All returned signals should be applicable to AD
    for signal in signals:
        metadata = SIGNAL_METADATA[signal]
        assert "AD" in metadata["applicable_segments"]


@pytest.mark.asyncio
async def test_get_signals_for_segment_autism(service, autism_context):
    """Test get_signals_for_segment for Autism."""
    signals = await service.get_signals_for_segment(autism_context)

    assert len(signals) > 0
    # All returned signals should be applicable to AU
    for signal in signals:
        metadata = SIGNAL_METADATA[signal]
        assert "AU" in metadata["applicable_segments"]


@pytest.mark.asyncio
async def test_get_signals_for_segment_audhd(service, audhd_context):
    """Test get_signals_for_segment for AuDHD."""
    signals = await service.get_signals_for_segment(audhd_context)

    # AuDHD should have most signals (includes both AD and AU signals)
    assert len(signals) > 10


@pytest.mark.asyncio
async def test_get_signals_for_segment_nt_empty(service, nt_context):
    """Test get_signals_for_segment for NT returns empty."""
    signals = await service.get_signals_for_segment(nt_context)
    assert len(signals) == 0  # NT has minimal tracking


@pytest.mark.asyncio
async def test_get_signals_for_segment_custom_all(service):
    """Test get_signals_for_segment for CU returns all signals."""
    cu_context = SegmentContext.from_code("CU")
    signals = await service.get_signals_for_segment(cu_context)

    # CU gets all signals (user decides)
    assert len(signals) == len(SIGNAL_METADATA)


# =============================================================================
# PatternDetectionService.get_cycle_summary Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_cycle_summary_empty(service):
    """Test get_cycle_summary for user with no history."""
    summary = await service.get_cycle_summary(user_id=999)

    assert summary["user_id"] == 999
    assert summary["total_cycles"] == 0
    assert summary["active_cycles"] == 0
    assert len(summary["cycles"]) == 0


@pytest.mark.asyncio
async def test_get_cycle_summary_after_detection(service, meta_spirale_data):
    """Test get_cycle_summary after detecting cycles."""
    await service.detect_cycles(user_id=1, recent_data=meta_spirale_data)
    summary = await service.get_cycle_summary(user_id=1)

    assert summary["user_id"] == 1
    assert summary["total_cycles"] == 5
    assert summary["active_cycles"] >= 1  # At least meta-spirale should be active


@pytest.mark.asyncio
async def test_get_cycle_summary_excludes_none_severity(service):
    """Test get_cycle_summary excludes NONE severity cycles."""
    # Provide enough social interactions to avoid triggering isolation detection
    # (social_interactions < 2 triggers ACTIVE isolation)
    neutral_data = {"social_interactions_count": 5}
    await service.detect_cycles(user_id=1, recent_data=neutral_data)
    summary = await service.get_cycle_summary(user_id=1)

    # All cycles should be NONE, so active_cycles = 0
    assert summary["active_cycles"] == 0


# =============================================================================
# Singleton Tests
# =============================================================================


def test_get_pattern_detection_service_singleton():
    """Test get_pattern_detection_service returns singleton."""
    service1 = get_pattern_detection_service()
    service2 = get_pattern_detection_service()
    assert service1 is service2


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_detect_cycles_with_missing_keys(service):
    """Test detect_cycles handles missing keys in recent_data."""
    incomplete_data = {"task_completion_rate": 0.3}
    cycles = await service.detect_cycles(user_id=1, recent_data=incomplete_data)

    # Should still return 5 cycles (with defaults)
    assert len(cycles) == 5


@pytest.mark.asyncio
async def test_detect_cycles_with_extreme_values(service):
    """Test detect_cycles handles extreme values."""
    # abandonment_ratio = abandoned / (new_starts + abandoned)
    # 9000 / (1000 + 9000) = 0.9 > 0.7 → SEVERE
    extreme_data = {
        "new_starts_count": 1000,
        "abandoned_tasks_count": 9000,
        "unpaid_work_hours": 100.0,
    }
    cycles = await service.detect_cycles(user_id=1, recent_data=extreme_data)

    # Should detect severe patterns
    shiny = next(c for c in cycles if c.cycle_type == CycleType.SHINY_OBJECT)
    free_work = next(c for c in cycles if c.cycle_type == CycleType.FREE_WORK)

    assert shiny.severity == CycleSeverity.SEVERE
    assert free_work.severity == CycleSeverity.SEVERE
