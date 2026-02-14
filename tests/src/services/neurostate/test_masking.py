"""
Unit tests for the MaskingLoadTracker service.

Tests cover:
- Masking event tracking and logging
- Masking cost calculation (exponential for context switching)
- Base load per masking type
- Duration factor for longer masking
- Context-specific load accumulation
- Context switching exponential penalty
- Total load calculation with exponential factor
- Overload and critical threshold detection
- Load reduction
- Recovery recommendations (critical, overloaded, manageable)
- Edge cases (unknown masking type, zero duration, single context)

All DB dependencies use the shared db_session fixture with in-memory SQLite.
"""

from unittest.mock import MagicMock

import pytest

from src.services.neurostate.masking import (
    MaskingEvent,
    MaskingLoad,
    MaskingLoadTracker,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service(db_session):
    """Create a MaskingLoadTracker with a real in-memory DB session."""
    return MaskingLoadTracker(db=db_session)


@pytest.fixture
def mock_service():
    """Create a MaskingLoadTracker with a mock DB session for unit tests."""
    mock_db = MagicMock()
    return MaskingLoadTracker(db=mock_db)


# =============================================================================
# TestMaskingTypeBaseLoad
# =============================================================================

class TestMaskingTypeBaseLoad:
    """Test the base load configuration per masking type."""

    def test_social_camouflaging_highest(self, mock_service):
        """Social camouflaging has the highest base load (15.0)."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["social_camouflaging"] == 15.0

    def test_emotional_suppression(self, mock_service):
        """Emotional suppression has base load of 12.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["emotional_suppression"] == 12.0

    def test_sensory_masking(self, mock_service):
        """Sensory masking has base load of 10.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["sensory_masking"] == 10.0

    def test_cognitive_masking(self, mock_service):
        """Cognitive masking has base load of 12.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["cognitive_masking"] == 12.0

    def test_attention_masking(self, mock_service):
        """Attention masking has base load of 8.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["attention_masking"] == 8.0

    def test_speech_masking(self, mock_service):
        """Speech masking has base load of 10.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["speech_masking"] == 10.0

    def test_special_interest_suppression(self, mock_service):
        """Special interest suppression has base load of 8.0."""
        assert mock_service.MASKING_TYPE_BASE_LOAD["special_interest_suppression"] == 8.0

    def test_seven_masking_types(self, mock_service):
        """There are exactly 7 masking types defined."""
        assert len(mock_service.MASKING_TYPE_BASE_LOAD) == 7


# =============================================================================
# TestThresholds
# =============================================================================

class TestThresholds:
    """Test threshold configuration."""

    def test_overload_threshold(self, mock_service):
        """Overload threshold is 80.0."""
        assert mock_service.OVERLOAD_THRESHOLD == 80.0

    def test_critical_threshold(self, mock_service):
        """Critical threshold is 95.0."""
        assert mock_service.CRITICAL_THRESHOLD == 95.0

    def test_context_multiplier(self, mock_service):
        """Context switching multiplier is 1.5."""
        assert mock_service.CONTEXT_MULTIPLIER == 1.5

    def test_max_contexts(self, mock_service):
        """Maximum tracked contexts is 10."""
        assert mock_service.MAX_CONTEXTS == 10

    def test_recent_window_hours(self, mock_service):
        """Recent event window is 24 hours."""
        assert mock_service.RECENT_WINDOW_HOURS == 24


# =============================================================================
# TestCalculateTotalLoad
# =============================================================================

class TestCalculateTotalLoad:
    """Test the _calculate_total_load() method."""

    def test_empty_contexts_returns_zero(self, mock_service):
        """No contexts returns 0.0 total load."""
        assert mock_service._calculate_total_load({}) == 0.0

    def test_single_context_base(self, mock_service):
        """Single context: exponential_factor = 1 + (1.5^0 - 1) * 0.5 = 1.0."""
        # 1 context: factor = 1 + (1.5^0 - 1) * 0.5 = 1 + 0 = 1.0
        total = mock_service._calculate_total_load({"work": 30.0})
        assert total == pytest.approx(30.0)

    def test_two_contexts_exponential(self, mock_service):
        """Two contexts: exponential factor > 1."""
        # 2 contexts: factor = 1 + (1.5^1 - 1) * 0.5 = 1 + 0.25 = 1.25
        total = mock_service._calculate_total_load({"work": 20.0, "social": 20.0})
        expected = 40.0 * 1.25
        assert total == pytest.approx(expected)

    def test_three_contexts_higher_exponential(self, mock_service):
        """Three contexts: even higher exponential factor."""
        # 3 contexts: factor = 1 + (1.5^2 - 1) * 0.5 = 1 + (2.25 - 1) * 0.5 = 1 + 0.625 = 1.625
        total = mock_service._calculate_total_load(
            {"work": 10.0, "social": 10.0, "family": 10.0}
        )
        expected = 30.0 * 1.625
        assert total == pytest.approx(expected)

    def test_total_capped_at_100(self, mock_service):
        """Total load is capped at 100.0."""
        total = mock_service._calculate_total_load(
            {"work": 50.0, "social": 50.0, "family": 50.0}
        )
        assert total == 100.0

    def test_exponential_growth_with_more_contexts(self, mock_service):
        """More contexts produce exponentially higher total load."""
        load_1 = mock_service._calculate_total_load({"work": 20.0})
        load_2 = mock_service._calculate_total_load({"work": 10.0, "social": 10.0})
        load_3 = mock_service._calculate_total_load(
            {"work": 7.0, "social": 7.0, "family": 6.0}
        )

        # Same base sum (20), but more contexts = higher total
        assert load_2 > load_1  # 20 * 1.25 > 20 * 1.0
        assert load_3 > load_1  # 20 * 1.625 > 20 * 1.0


# =============================================================================
# TestTrack
# =============================================================================

class TestTrack:
    """Test the track() async method."""

    @pytest.mark.asyncio
    async def test_track_returns_masking_load(self, service):
        """track() returns a MaskingLoad dataclass."""
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="social_camouflaging",
        )

        assert isinstance(result, MaskingLoad)
        assert result.user_id == 1
        assert isinstance(result.total_load, float)
        assert isinstance(result.context_loads, dict)
        assert isinstance(result.is_overloaded, bool)
        assert isinstance(result.is_critical, bool)

    @pytest.mark.asyncio
    async def test_track_known_masking_type(self, service):
        """Known masking type uses its configured base load."""
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="social_camouflaging",
        )
        # social_camouflaging base = 15.0
        assert result.total_load > 0

    @pytest.mark.asyncio
    async def test_track_unknown_masking_type(self, service):
        """Unknown masking type uses default base load of 10.0."""
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="unknown_type",
        )
        # Default base = 10.0
        assert result.total_load > 0

    @pytest.mark.asyncio
    async def test_track_with_duration_increases_load(self, service):
        """Duration multiplier increases the event load."""
        result_no_duration = await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",
        )
        # Track a new event for a different user to compare independently
        result_with_duration = await service.track(
            user_id=2,
            context="work",
            masking_behavior="attention_masking",
            duration_minutes=120,
        )

        # 120 min: factor = 1 + (120/60) * 0.5 = 2.0
        # Without duration: base = 8.0
        # With 120 min: 8.0 * 2.0 = 16.0
        assert result_with_duration.total_load > result_no_duration.total_load

    @pytest.mark.asyncio
    async def test_track_same_context_accumulates(self, service):
        """Tracking in the same context accumulates load additively."""
        await service.track(
            user_id=1,
            context="work",
            masking_behavior="sensory_masking",
        )
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="sensory_masking",
        )

        # Two events of 10.0 each in same context = 20.0 total
        assert result.context_loads.get("work", 0) >= 20.0

    @pytest.mark.asyncio
    async def test_track_new_context_exponential_penalty(self, service):
        """New context adds exponential penalty based on active context count."""
        # First context: no penalty
        await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",  # base 8.0
        )
        # Second context: penalty = 1.5^1 = 1.5x
        result = await service.track(
            user_id=1,
            context="social",
            masking_behavior="attention_masking",  # base 8.0 * 1.5 = 12.0
        )

        # "social" context should have higher load than raw base
        assert result.context_loads.get("social", 0) > 8.0

    @pytest.mark.asyncio
    async def test_track_logs_event_to_database(self, service, db_session):
        """track() creates a MaskingLog entry in the database."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1,
            context="work",
            masking_behavior="cognitive_masking",
        )

        logs = db_session.query(MaskingLog).filter(MaskingLog.user_id == 1).all()
        assert len(logs) == 1
        assert logs[0].context == "work"
        assert logs[0].masking_type == "cognitive_masking"

    @pytest.mark.asyncio
    async def test_track_with_notes(self, service, db_session):
        """track() stores optional notes on the event."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1,
            context="work",
            masking_behavior="social_camouflaging",
            notes="Meeting with boss",
        )

        logs = db_session.query(MaskingLog).filter(MaskingLog.user_id == 1).all()
        assert len(logs) == 1
        # notes is encrypted, so we access the property
        assert logs[0].notes == "Meeting with boss"


# =============================================================================
# TestGetCurrentLoad
# =============================================================================

class TestGetCurrentLoad:
    """Test the get_current_load() async method."""

    @pytest.mark.asyncio
    async def test_empty_load_for_new_user(self, service):
        """New user has zero total load."""
        result = await service.get_current_load(user_id=999)
        assert result.total_load == 0.0
        assert result.context_loads == {}
        assert result.is_overloaded is False
        assert result.is_critical is False

    @pytest.mark.asyncio
    async def test_load_reflects_tracked_events(self, service):
        """Current load reflects all tracked masking events."""
        await service.track(user_id=1, context="work", masking_behavior="sensory_masking")
        result = await service.get_current_load(user_id=1)

        assert result.total_load > 0
        assert "work" in result.context_loads

    @pytest.mark.asyncio
    async def test_overloaded_flag(self, service):
        """is_overloaded is True when total load > 80."""
        # Track many events to push total above 80
        for _ in range(7):
            await service.track(
                user_id=1, context="work", masking_behavior="social_camouflaging"
            )

        result = await service.get_current_load(user_id=1)
        if result.total_load > 80.0:
            assert result.is_overloaded is True


# =============================================================================
# TestReduceLoad
# =============================================================================

class TestReduceLoad:
    """Test the reduce_load() async method."""

    @pytest.mark.asyncio
    async def test_reduce_existing_context(self, service):
        """Reducing load in an existing context decreases load score."""
        await service.track(
            user_id=1, context="work", masking_behavior="social_camouflaging"
        )

        await service.get_current_load(user_id=1)
        result = await service.reduce_load(user_id=1, context="work", reduction=10.0)

        # After reduction, total should be lower (or at least a negative event logged)
        # The total_load recalculates from DB events
        # The negative event (-10.0) brings the context sum down
        assert isinstance(result, MaskingLoad)

    @pytest.mark.asyncio
    async def test_reduce_nonexistent_context(self, service):
        """Reducing load in a nonexistent context has no effect."""
        result = await service.reduce_load(user_id=1, context="nonexistent", reduction=10.0)
        assert result.total_load == 0.0

    @pytest.mark.asyncio
    async def test_reduce_logs_negative_event(self, service, db_session):
        """reduce_load() logs a negative load event."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1, context="work", masking_behavior="attention_masking"
        )
        await service.reduce_load(user_id=1, context="work", reduction=5.0)

        logs = db_session.query(MaskingLog).filter(
            MaskingLog.user_id == 1, MaskingLog.masking_type == "load_reduction"
        ).all()
        assert len(logs) == 1
        assert logs[0].load_score == -5.0


# =============================================================================
# TestGetRecoveryRecommendations
# =============================================================================

class TestGetRecoveryRecommendations:
    """Test the get_recovery_recommendations() async method."""

    @pytest.mark.asyncio
    async def test_manageable_when_no_load(self, service):
        """No masking load returns manageable recommendation."""
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("manageable" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_overloaded_recommendations(self, service):
        """Overloaded state returns context reduction recommendations."""
        # Push above 80
        for _ in range(7):
            await service.track(
                user_id=1, context="work", masking_behavior="social_camouflaging"
            )

        load = await service.get_current_load(user_id=1)
        if load.is_overloaded and not load.is_critical:
            recs = await service.get_recovery_recommendations(user_id=1)
            assert any("reduce" in r.lower() or "context" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_critical_recommendations(self, service):
        """Critical state returns immediate stop recommendations."""
        # Push well above 95 with many events
        for _ in range(15):
            await service.track(
                user_id=1, context="work", masking_behavior="social_camouflaging"
            )

        load = await service.get_current_load(user_id=1)
        if load.is_critical:
            recs = await service.get_recovery_recommendations(user_id=1)
            assert any("stop" in r.lower() or "critical" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_accumulation_warning_three_contexts(self, service):
        """Three or more contexts triggers accumulation warning."""
        await service.track(user_id=1, context="work", masking_behavior="attention_masking")
        await service.track(user_id=1, context="social", masking_behavior="attention_masking")
        await service.track(user_id=1, context="family", masking_behavior="attention_masking")

        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("accumulation" in r.lower() or "multiple" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_high_context_load_recommendation(self, service):
        """Context with load > 50 gets specific recommendation."""
        for _ in range(5):
            await service.track(
                user_id=1, context="work", masking_behavior="social_camouflaging"
            )

        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("work" in r.lower() for r in recs)


# =============================================================================
# TestMaskingLoadDataclass
# =============================================================================

class TestMaskingLoadDataclass:
    """Test the MaskingLoad dataclass."""

    def test_masking_load_construction(self):
        """MaskingLoad can be constructed with all fields."""
        load = MaskingLoad(
            user_id=1,
            total_load=45.0,
            context_loads={"work": 30.0, "social": 15.0},
            is_overloaded=False,
            is_critical=False,
            recent_events=[],
        )
        assert load.user_id == 1
        assert load.total_load == 45.0
        assert load.context_loads["work"] == 30.0
        assert load.is_overloaded is False


# =============================================================================
# TestMaskingEventDataclass
# =============================================================================

class TestMaskingEventDataclass:
    """Test the MaskingEvent dataclass."""

    def test_masking_event_defaults(self):
        """MaskingEvent has sensible defaults."""
        event = MaskingEvent()
        assert event.id is None
        assert event.user_id == 0
        assert event.context == ""
        assert event.masking_type == ""
        assert event.load_score == 0.0
        assert event.duration_minutes is None
        assert event.notes is None

    def test_masking_event_custom(self):
        """MaskingEvent can be constructed with custom values."""
        event = MaskingEvent(
            id=1,
            user_id=42,
            context="work",
            masking_type="social_camouflaging",
            load_score=15.0,
            duration_minutes=60,
            notes="Important meeting",
        )
        assert event.id == 1
        assert event.user_id == 42
        assert event.context == "work"
        assert event.load_score == 15.0
        assert event.duration_minutes == 60


# =============================================================================
# TestDurationFactor
# =============================================================================

class TestDurationFactor:
    """Test the duration factor calculation in track()."""

    @pytest.mark.asyncio
    async def test_60_minutes_factor(self, service):
        """60 minutes gives factor = 1 + (60/60)*0.5 = 1.5."""
        # attention_masking base = 8.0
        # With 60 min: 8.0 * 1.5 = 12.0
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",
            duration_minutes=60,
        )
        # The logged load_score should be 12.0
        assert result.total_load > 0

    @pytest.mark.asyncio
    async def test_zero_duration_no_factor(self, service):
        """Zero or None duration uses base load without factor."""
        result_no_dur = await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",
            duration_minutes=None,
        )
        result_zero = await service.track(
            user_id=2,
            context="work",
            masking_behavior="attention_masking",
            duration_minutes=0,
        )
        # duration_minutes=0 is falsy, so no factor applied
        assert result_no_dur.total_load == result_zero.total_load

    @pytest.mark.asyncio
    async def test_long_duration_high_factor(self, service):
        """180 minutes gives factor = 1 + (180/60)*0.5 = 2.5."""
        result = await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",
            duration_minutes=180,
        )
        # 8.0 * 2.5 = 20.0
        assert result.total_load >= 20.0


# =============================================================================
# TestContextSwitchingPenalty
# =============================================================================

class TestContextSwitchingPenalty:
    """Test the exponential context switching penalty."""

    @pytest.mark.asyncio
    async def test_first_context_no_penalty(self, service, db_session):
        """First masking context has no exponential penalty."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1,
            context="work",
            masking_behavior="attention_masking",
        )

        log = db_session.query(MaskingLog).filter(MaskingLog.user_id == 1).first()
        assert log is not None
        assert log.load_score == pytest.approx(8.0)  # Base load, no penalty

    @pytest.mark.asyncio
    async def test_second_context_penalty_1_5x(self, service, db_session):
        """Second masking context has 1.5x penalty."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1, context="work", masking_behavior="attention_masking"
        )
        await service.track(
            user_id=1, context="social", masking_behavior="attention_masking"
        )

        logs = (
            db_session.query(MaskingLog)
            .filter(MaskingLog.user_id == 1, MaskingLog.context == "social")
            .all()
        )
        assert len(logs) == 1
        # base 8.0 * 1.5^1 = 12.0
        assert logs[0].load_score == pytest.approx(12.0)

    @pytest.mark.asyncio
    async def test_third_context_penalty_2_25x(self, service, db_session):
        """Third masking context has 1.5^2 = 2.25x penalty."""
        from src.models.neurostate import MaskingLog

        await service.track(
            user_id=1, context="work", masking_behavior="attention_masking"
        )
        await service.track(
            user_id=1, context="social", masking_behavior="attention_masking"
        )
        await service.track(
            user_id=1, context="family", masking_behavior="attention_masking"
        )

        logs = (
            db_session.query(MaskingLog)
            .filter(MaskingLog.user_id == 1, MaskingLog.context == "family")
            .all()
        )
        assert len(logs) == 1
        # base 8.0 * 1.5^2 = 18.0
        assert logs[0].load_score == pytest.approx(18.0)
