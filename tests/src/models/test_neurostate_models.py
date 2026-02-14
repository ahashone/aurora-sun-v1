"""
Tests for neurostate models.

Tests all 6 neurostate models:
- SensoryProfile
- MaskingLog
- BurnoutAssessment
- ChannelState
- InertiaEvent
- EnergyLevelRecord

Covers:
- Model creation and relationships
- Property accessors (encrypted fields)
- Enum values
- Repr methods
- Database constraints
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.neurostate import (
    BurnoutAssessment,
    BurnoutType,
    ChannelState,
    ChannelType,
    EnergyLevel,
    EnergyLevelRecord,
    InertiaEvent,
    InertiaType,
    MaskingLog,
    SensoryProfile,
)
from src.models.session import Session
from src.models.user import User


# =============================================================================
# Enum Tests
# =============================================================================


def test_inertia_type_enum():
    """Test InertiaType enum values."""
    assert InertiaType.AUTISTIC_INERTIA == "autistic_inertia"
    assert InertiaType.ACTIVATION_DEFICIT == "activation_deficit"
    assert InertiaType.DOUBLE_BLOCK == "double_block"


def test_burnout_type_enum():
    """Test BurnoutType enum values."""
    assert BurnoutType.AD_BOOM_BUST == "ad_boom_bust"
    assert BurnoutType.AU_OVERLOAD == "au_overload"
    assert BurnoutType.AH_TRIPLE == "ah_triple"


def test_channel_type_enum():
    """Test ChannelType enum values."""
    assert ChannelType.FOCUS == "focus"
    assert ChannelType.CREATIVE == "creative"
    assert ChannelType.SOCIAL == "social"
    assert ChannelType.PHYSICAL == "physical"
    assert ChannelType.LEARNING == "learning"


def test_energy_level_enum():
    """Test EnergyLevel enum values."""
    assert EnergyLevel.CRITICAL == "critical"
    assert EnergyLevel.LOW == "low"
    assert EnergyLevel.BASELINE == "baseline"
    assert EnergyLevel.ELEVATED == "elevated"
    assert EnergyLevel.HYPERFOCUS == "hyperfocus"


# =============================================================================
# SensoryProfile Tests
# =============================================================================


def test_sensory_profile_creation(db_session):
    """Test creating a sensory profile."""
    user = User(telegram_id="test123", name="Test User")
    db_session.add(user)
    db_session.commit()

    profile = SensoryProfile(
        user_id=user.id,
        overall_load=65.5,
        segment_code="AU",
    )
    profile.modality_loads = {"visual": 70, "auditory": 80, "tactile": 50}

    db_session.add(profile)
    db_session.commit()

    assert profile.id is not None
    assert profile.user_id == user.id
    assert profile.overall_load == 65.5
    assert profile.segment_code == "AU"
    assert profile.modality_loads == {"visual": 70, "auditory": 80, "tactile": 50}


def test_sensory_profile_modality_loads_encryption(db_session, encryption_service):
    """Test modality loads encryption."""
    user = User(telegram_id="test456", name="Test User")
    db_session.add(user)
    db_session.commit()

    profile = SensoryProfile(user_id=user.id)
    loads = {"visual": 60, "auditory": 70}
    profile.modality_loads = loads

    db_session.add(profile)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(SensoryProfile).filter_by(id=profile.id).first()
    assert retrieved.modality_loads == loads


def test_sensory_profile_modality_loads_empty(db_session):
    """Test sensory profile with no modality loads."""
    user = User(telegram_id="test789", name="Test User")
    db_session.add(user)
    db_session.commit()

    profile = SensoryProfile(user_id=user.id)
    db_session.add(profile)
    db_session.commit()

    assert profile.modality_loads == {}


def test_sensory_profile_repr(db_session):
    """Test SensoryProfile repr."""
    user = User(telegram_id="test999", name="Test User")
    db_session.add(user)
    db_session.commit()

    profile = SensoryProfile(user_id=user.id, overall_load=42.3)
    assert repr(profile) == f"<SensoryProfile(user_id={user.id}, overall_load=42.3)>"


# =============================================================================
# MaskingLog Tests
# =============================================================================


def test_masking_log_creation(db_session):
    """Test creating a masking log entry."""
    user = User(telegram_id="mask123", name="Test User")
    db_session.add(user)
    db_session.commit()

    log = MaskingLog(
        user_id=user.id,
        context="work",
        masking_type="camouflaging",
        load_score=75.0,
        duration_minutes=180,
    )
    log.notes = "Very exhausting meeting"

    db_session.add(log)
    db_session.commit()

    assert log.id is not None
    assert log.user_id == user.id
    assert log.context == "work"
    assert log.masking_type == "camouflaging"
    assert log.load_score == 75.0
    assert log.duration_minutes == 180
    assert log.notes == "Very exhausting meeting"


def test_masking_log_notes_encryption(db_session, encryption_service):
    """Test masking log notes encryption."""
    user = User(telegram_id="mask456", name="Test User")
    db_session.add(user)
    db_session.commit()

    log = MaskingLog(user_id=user.id, context="social", masking_type="mirroring")
    log.notes = "Pretended to be interested in small talk"

    db_session.add(log)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(MaskingLog).filter_by(id=log.id).first()
    assert retrieved.notes == "Pretended to be interested in small talk"


def test_masking_log_notes_none(db_session):
    """Test masking log with no notes."""
    user = User(telegram_id="mask789", name="Test User")
    db_session.add(user)
    db_session.commit()

    log = MaskingLog(user_id=user.id, context="family", masking_type="suppression")
    db_session.add(log)
    db_session.commit()

    assert log.notes is None


def test_masking_log_repr(db_session):
    """Test MaskingLog repr."""
    user = User(telegram_id="mask999", name="Test User")
    db_session.add(user)
    db_session.commit()

    log = MaskingLog(user_id=user.id, context="work", masking_type="test", load_score=80.5)
    expected = f"<MaskingLog(user_id={user.id}, context=work, load=80.5)>"
    assert repr(log) == expected


# =============================================================================
# BurnoutAssessment Tests
# =============================================================================


def test_burnout_assessment_creation(db_session):
    """Test creating a burnout assessment."""
    user = User(telegram_id="burnout123", name="Test User")
    db_session.add(user)
    db_session.commit()

    assessment = BurnoutAssessment(
        user_id=user.id,
        burnout_type=BurnoutType.AD_BOOM_BUST,
        severity_score=85.0,
        indicators={"sleep_disruption": True, "executive_function_loss": True},
    )
    assessment.energy_trajectory = [80, 75, 60, 40, 20]
    assessment.notes = "Classic boom-bust cycle after project deadline"

    db_session.add(assessment)
    db_session.commit()

    assert assessment.id is not None
    assert assessment.user_id == user.id
    assert assessment.burnout_type == BurnoutType.AD_BOOM_BUST
    assert assessment.severity_score == 85.0
    assert assessment.energy_trajectory == [80, 75, 60, 40, 20]
    assert assessment.notes == "Classic boom-bust cycle after project deadline"


def test_burnout_assessment_energy_trajectory_encryption(db_session, encryption_service):
    """Test energy trajectory encryption."""
    user = User(telegram_id="burnout456", name="Test User")
    db_session.add(user)
    db_session.commit()

    assessment = BurnoutAssessment(
        user_id=user.id,
        burnout_type=BurnoutType.AU_OVERLOAD,
        severity_score=90.0,
    )
    trajectory = [70, 65, 55, 40, 30, 15]
    assessment.energy_trajectory = trajectory

    db_session.add(assessment)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(BurnoutAssessment).filter_by(id=assessment.id).first()
    assert retrieved.energy_trajectory == trajectory


def test_burnout_assessment_resolution(db_session):
    """Test marking burnout as resolved."""
    user = User(telegram_id="burnout789", name="Test User")
    db_session.add(user)
    db_session.commit()

    assessment = BurnoutAssessment(
        user_id=user.id,
        burnout_type=BurnoutType.AH_TRIPLE,
        severity_score=95.0,
    )
    db_session.add(assessment)
    db_session.commit()

    # Mark as resolved
    assessment.resolved_at = datetime.now(UTC)
    db_session.commit()

    assert assessment.resolved_at is not None


def test_burnout_assessment_repr(db_session):
    """Test BurnoutAssessment repr."""
    user = User(telegram_id="burnout999", name="Test User")
    db_session.add(user)
    db_session.commit()

    assessment = BurnoutAssessment(
        user_id=user.id,
        burnout_type=BurnoutType.AD_BOOM_BUST,
        severity_score=77.5,
    )
    expected = f"<BurnoutAssessment(user_id={user.id}, type=ad_boom_bust, severity=77.5)>"
    assert repr(assessment) == expected


# =============================================================================
# ChannelState Tests
# =============================================================================


def test_channel_state_creation(db_session):
    """Test creating a channel state."""
    user = User(telegram_id="channel123", name="Test User")
    db_session.add(user)
    db_session.commit()

    state = ChannelState(
        user_id=user.id,
        dominant_channel=ChannelType.FOCUS,
        channel_scores={"focus": 85, "creative": 40, "social": 30},
        confidence=0.85,
        supporting_signals={"short_messages": True, "deep_work": True},
    )

    db_session.add(state)
    db_session.commit()

    assert state.id is not None
    assert state.user_id == user.id
    assert state.dominant_channel == ChannelType.FOCUS
    assert state.channel_scores == {"focus": 85, "creative": 40, "social": 30}
    assert state.confidence == 0.85


def test_channel_state_period_tracking(db_session):
    """Test channel state period tracking."""
    user = User(telegram_id="channel456", name="Test User")
    db_session.add(user)
    db_session.commit()

    now = datetime.now(UTC)
    later = now + timedelta(hours=3)

    state = ChannelState(
        user_id=user.id,
        dominant_channel=ChannelType.CREATIVE,
        channel_scores={"creative": 90, "focus": 50},
        period_start=now,
        period_end=later,
    )

    db_session.add(state)
    db_session.commit()

    # Check timestamps (remove microseconds and tzinfo for comparison due to DB precision
    # and SQLite not storing timezone info)
    assert state.period_start.replace(microsecond=0, tzinfo=None) == now.replace(microsecond=0, tzinfo=None)
    assert state.period_end.replace(microsecond=0, tzinfo=None) == later.replace(microsecond=0, tzinfo=None)


def test_channel_state_repr(db_session):
    """Test ChannelState repr."""
    user = User(telegram_id="channel999", name="Test User")
    db_session.add(user)
    db_session.commit()

    state = ChannelState(
        user_id=user.id,
        dominant_channel=ChannelType.SOCIAL,
        channel_scores={},
        confidence=0.72,
    )
    expected = f"<ChannelState(user_id={user.id}, dominant=social, confidence=0.72)>"
    assert repr(state) == expected


# =============================================================================
# InertiaEvent Tests
# =============================================================================


def test_inertia_event_creation(db_session):
    """Test creating an inertia event."""
    user = User(telegram_id="inertia123", name="Test User")
    db_session.add(user)
    db_session.commit()

    event = InertiaEvent(
        user_id=user.id,
        inertia_type=InertiaType.AUTISTIC_INERTIA,
        severity=80.0,
        trigger="context_switch",
        attempted_interventions=["body_doubling", "minimal_viable_action"],
        outcome="resolved",
        duration_minutes=45,
    )
    event.notes = "Needed body doubling to switch from email to coding"

    db_session.add(event)
    db_session.commit()

    assert event.id is not None
    assert event.user_id == user.id
    assert event.inertia_type == InertiaType.AUTISTIC_INERTIA
    assert event.severity == 80.0
    assert event.trigger == "context_switch"
    assert event.outcome == "resolved"
    assert event.duration_minutes == 45


def test_inertia_event_notes_encryption(db_session, encryption_service):
    """Test inertia event notes encryption."""
    user = User(telegram_id="inertia456", name="Test User")
    db_session.add(user)
    db_session.commit()

    event = InertiaEvent(
        user_id=user.id,
        inertia_type=InertiaType.ACTIVATION_DEFICIT,
        severity=70.0,
    )
    event.notes = "Could not start task despite deadline"

    db_session.add(event)
    db_session.commit()

    # Retrieve and verify
    retrieved = db_session.query(InertiaEvent).filter_by(id=event.id).first()
    assert retrieved.notes == "Could not start task despite deadline"


def test_inertia_event_resolution_tracking(db_session):
    """Test tracking inertia event resolution."""
    user = User(telegram_id="inertia789", name="Test User")
    db_session.add(user)
    db_session.commit()

    event = InertiaEvent(
        user_id=user.id,
        inertia_type=InertiaType.DOUBLE_BLOCK,
        severity=95.0,
    )
    db_session.add(event)
    db_session.commit()

    # Mark as resolved
    event.resolved_at = datetime.now(UTC)
    event.outcome = "resolved"
    db_session.commit()

    assert event.resolved_at is not None
    assert event.outcome == "resolved"


def test_inertia_event_repr(db_session):
    """Test InertiaEvent repr."""
    user = User(telegram_id="inertia999", name="Test User")
    db_session.add(user)
    db_session.commit()

    event = InertiaEvent(
        user_id=user.id,
        inertia_type=InertiaType.ACTIVATION_DEFICIT,
        severity=65.5,
    )
    expected = f"<InertiaEvent(user_id={user.id}, type=activation_deficit, severity=65.5)>"
    assert repr(event) == expected


# =============================================================================
# EnergyLevelRecord Tests
# =============================================================================


def test_energy_level_record_creation(db_session):
    """Test creating an energy level record."""
    user = User(telegram_id="energy123", name="Test User")
    db_session.add(user)
    db_session.commit()

    session = Session(user_id=user.id)
    db_session.add(session)
    db_session.commit()

    record = EnergyLevelRecord(
        user_id=user.id,
        session_id=session.id,
        energy_level=EnergyLevel.ELEVATED,
        energy_score=75.0,
        behavioral_proxies={
            "response_latency_ms": 200,
            "message_length": 150,
            "vocabulary_complexity": "medium",
        },
    )

    db_session.add(record)
    db_session.commit()

    assert record.id is not None
    assert record.user_id == user.id
    assert record.session_id == session.id
    assert record.energy_level == EnergyLevel.ELEVATED
    assert record.energy_score == 75.0


def test_energy_level_record_behavioral_proxies(db_session):
    """Test behavioral proxies tracking."""
    user = User(telegram_id="energy456", name="Test User")
    db_session.add(user)
    db_session.commit()

    record = EnergyLevelRecord(
        user_id=user.id,
        energy_level=EnergyLevel.HYPERFOCUS,
        energy_score=95.0,
        behavioral_proxies={
            "response_latency_ms": 50,
            "message_length": 300,
            "vocabulary_complexity": "high",
            "time_of_day": "morning",
        },
    )

    db_session.add(record)
    db_session.commit()

    assert "response_latency_ms" in record.behavioral_proxies
    assert record.behavioral_proxies["response_latency_ms"] == 50


def test_energy_level_record_without_session(db_session):
    """Test energy level record without session."""
    user = User(telegram_id="energy789", name="Test User")
    db_session.add(user)
    db_session.commit()

    record = EnergyLevelRecord(
        user_id=user.id,
        energy_level=EnergyLevel.LOW,
        energy_score=30.0,
    )

    db_session.add(record)
    db_session.commit()

    assert record.session_id is None


def test_energy_level_record_repr(db_session):
    """Test EnergyLevelRecord repr."""
    user = User(telegram_id="energy999", name="Test User")
    db_session.add(user)
    db_session.commit()

    record = EnergyLevelRecord(
        user_id=user.id,
        energy_level=EnergyLevel.BASELINE,
        energy_score=50.5,
    )
    expected = f"<EnergyLevelRecord(user_id={user.id}, level=baseline, score=50.5)>"
    assert repr(record) == expected


# =============================================================================
# Integration Tests
# =============================================================================


def test_multiple_neurostate_models_for_user(db_session):
    """Test that a user can have multiple neurostate records."""
    user = User(telegram_id="multi123", name="Test User")
    db_session.add(user)
    db_session.commit()

    # Add sensory profile
    sensory = SensoryProfile(user_id=user.id, overall_load=60.0)
    db_session.add(sensory)

    # Add masking log
    masking = MaskingLog(user_id=user.id, context="work", masking_type="camouflaging")
    db_session.add(masking)

    # Add burnout assessment
    burnout = BurnoutAssessment(
        user_id=user.id,
        burnout_type=BurnoutType.AH_TRIPLE,
        severity_score=80.0,
    )
    db_session.add(burnout)

    # Add energy record
    energy = EnergyLevelRecord(
        user_id=user.id,
        energy_level=EnergyLevel.LOW,
        energy_score=35.0,
    )
    db_session.add(energy)

    db_session.commit()

    # Verify all records exist
    assert db_session.query(SensoryProfile).filter_by(user_id=user.id).count() == 1
    assert db_session.query(MaskingLog).filter_by(user_id=user.id).count() == 1
    assert db_session.query(BurnoutAssessment).filter_by(user_id=user.id).count() == 1
    assert db_session.query(EnergyLevelRecord).filter_by(user_id=user.id).count() == 1
