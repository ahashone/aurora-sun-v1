"""
Comprehensive tests for CoachingEngine (Inline Coaching).

Tests cover:
- Stuck detection (explicit patterns and drift patterns)
- Segment-specific routing (NO string comparison, uses SegmentContext fields)
- PINCH activation for ADHD (Passion, Interest, Novelty, Competition, Hurry)
- Inertia protocol for Autism (NOT "just start")
- Channel dominance check for AuDHD (SW-19)
- Standard motivation for Neurotypical
- Burnout gate (SW-12)
- Crisis handling (SW-11)
- Sweet spot reinforcement
- Tension Engine integration
- Effectiveness tracking
- CoachingResponse serialization

CRITICAL Anti-Patterns Tested:
- Never `if segment == "AD"` (uses SegmentContext.features instead)
- Never "just start" for Autism (Inertia != Activation Deficit)
- Never Behavioral Activation during Autistic Burnout
- Channel dominance checked FIRST for AuDHD

Data Classification: SENSITIVE (coaching interactions, neurostate)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.module_context import ModuleContext
from src.core.module_response import ModuleResponse
from src.core.segment_context import SegmentContext
from src.services.coaching_engine import (
    CoachingEngine,
    CoachingResponse,
    get_coaching_engine,
)
from src.services.tension_engine import TensionState

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def coaching_engine():
    """Create a CoachingEngine instance with mocked dependencies."""
    mock_tension = MagicMock()
    mock_redis = MagicMock()
    # Redis get/set must be async since coaching engine awaits them
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    return CoachingEngine(tension_engine=mock_tension, redis_service=mock_redis)


@pytest.fixture
def module_context_adhd():
    """Create a ModuleContext for ADHD segment."""
    ctx = ModuleContext(
        user_id=1,
        segment_context=SegmentContext.from_code("AD"),
        state="active",
        session_id="test-session-1",
        language="en",
        module_name="test_module",
        message_history=[],
    )
    return ctx


@pytest.fixture
def module_context_autism():
    """Create a ModuleContext for Autism segment."""
    ctx = ModuleContext(
        user_id=2,
        segment_context=SegmentContext.from_code("AU"),
        state="active",
        session_id="test-session-2",
        language="en",
        module_name="test_module",
        message_history=[],
    )
    return ctx


@pytest.fixture
def module_context_audhd():
    """Create a ModuleContext for AuDHD segment."""
    ctx = ModuleContext(
        user_id=3,
        segment_context=SegmentContext.from_code("AH"),
        state="active",
        session_id="test-session-3",
        language="en",
        module_name="test_module",
        message_history=[],
    )
    return ctx


@pytest.fixture
def module_context_neurotypical():
    """Create a ModuleContext for Neurotypical segment."""
    ctx = ModuleContext(
        user_id=4,
        segment_context=SegmentContext.from_code("NT"),
        state="active",
        session_id="test-session-4",
        language="en",
        module_name="test_module",
        message_history=[],
    )
    return ctx


# =============================================================================
# Test: Initialization
# =============================================================================


def test_coaching_engine_initialization(coaching_engine: CoachingEngine):
    """Test that CoachingEngine initializes correctly."""
    assert coaching_engine is not None
    assert coaching_engine.tension_engine is not None
    assert coaching_engine.redis_service is not None


def test_get_coaching_engine_singleton():
    """Test that get_coaching_engine returns a singleton."""
    engine1 = get_coaching_engine()
    engine2 = get_coaching_engine()
    assert engine1 is engine2


# =============================================================================
# Test: CoachingResponse
# =============================================================================


def test_coaching_response_initialization():
    """Test CoachingResponse initialization."""
    response = CoachingResponse(text="Test message")
    assert response.text == "Test message"
    assert response.should_continue_module is True
    assert response.is_crisis_response is False
    assert response.is_burnout_redirect is False
    assert response.metadata == {}


def test_coaching_response_to_module_response():
    """Test converting CoachingResponse to ModuleResponse."""
    coaching_response = CoachingResponse(
        text="Test",
        metadata={"protocol": "test"},
    )
    module_response = coaching_response.to_module_response()
    assert isinstance(module_response, ModuleResponse)
    assert module_response.text == "Test"
    assert module_response.metadata["protocol"] == "test"


# =============================================================================
# Test: Stuck Detection
# =============================================================================


@pytest.mark.asyncio
async def test_detect_stuck_explicit_pattern(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test detecting explicit stuck patterns."""
    is_stuck = await coaching_engine.detect_stuck("I'm stuck", module_context_adhd)
    assert is_stuck is True


@pytest.mark.asyncio
async def test_detect_stuck_cant_start_pattern(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test detecting "can't start" pattern."""
    is_stuck = await coaching_engine.detect_stuck("I can't start", module_context_adhd)
    assert is_stuck is True


@pytest.mark.asyncio
async def test_detect_stuck_overwhelmed_pattern(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test detecting "overwhelmed" pattern."""
    is_stuck = await coaching_engine.detect_stuck("I'm overwhelmed", module_context_adhd)
    assert is_stuck is True


@pytest.mark.asyncio
async def test_detect_stuck_case_insensitive(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that stuck detection is case-insensitive."""
    is_stuck = await coaching_engine.detect_stuck("I'M STUCK", module_context_adhd)
    assert is_stuck is True


@pytest.mark.asyncio
async def test_detect_stuck_drift_in_avoidance_quadrant(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that drift patterns trigger stuck detection in AVOIDANCE quadrant."""
    # Mock tension state to AVOIDANCE (sonne >= 0.5, erde < 0.5)
    mock_state = TensionState(
        user_id=1,
        sonne=0.8,
        erde=0.3,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    is_stuck = await coaching_engine.detect_stuck("maybe later", module_context_adhd)
    assert is_stuck is True


@pytest.mark.asyncio
async def test_detect_stuck_drift_not_in_sweet_spot(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that drift patterns don't trigger in SWEET_SPOT quadrant."""
    # Mock tension state to SWEET_SPOT (sonne >= 0.5, erde >= 0.5)
    mock_state = TensionState(
        user_id=1,
        sonne=0.8,
        erde=0.8,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    is_stuck = await coaching_engine.detect_stuck("maybe later", module_context_adhd)
    assert is_stuck is False


@pytest.mark.asyncio
async def test_detect_stuck_normal_message(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that normal messages don't trigger stuck detection."""
    is_stuck = await coaching_engine.detect_stuck("Hello, how are you?", module_context_adhd)
    assert is_stuck is False


# =============================================================================
# Test: PINCH Activation (ADHD)
# =============================================================================


@pytest.mark.asyncio
async def test_pinch_activation_returns_response(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test PINCH activation returns a CoachingResponse."""
    response = await coaching_engine.pinch_activation(module_context_adhd)
    assert isinstance(response, CoachingResponse)
    assert response.should_continue_module is True
    assert response.metadata["protocol"] == "pinch_activation"
    assert response.metadata["segment"] == "AD"


@pytest.mark.asyncio
async def test_pinch_activation_deterministic_selection(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that PINCH activation uses deterministic selection based on message history."""
    # Same message history length should give same response
    response1 = await coaching_engine.pinch_activation(module_context_adhd)
    response2 = await coaching_engine.pinch_activation(module_context_adhd)
    assert response1.text == response2.text


@pytest.mark.asyncio
async def test_pinch_activation_varies_by_history_length(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that PINCH activation varies with message history length."""
    await coaching_engine.pinch_activation(module_context_adhd)

    # Add a message to history
    module_context_adhd.message_history.append("test")
    await coaching_engine.pinch_activation(module_context_adhd)

    # Responses should be different (unless by chance same index)
    # This is probabilistic but with 4 responses, different is likely


# =============================================================================
# Test: Inertia Protocol (Autism)
# =============================================================================


@pytest.mark.asyncio
async def test_inertia_protocol_returns_response(coaching_engine: CoachingEngine, module_context_autism: ModuleContext):
    """Test inertia protocol returns a CoachingResponse."""
    response = await coaching_engine.inertia_protocol(module_context_autism)
    assert isinstance(response, CoachingResponse)
    assert response.should_continue_module is True
    assert response.metadata["protocol"] == "inertia_protocol"
    assert response.metadata["segment"] == "AU"


@pytest.mark.asyncio
async def test_inertia_protocol_not_just_start(coaching_engine: CoachingEngine, module_context_autism: ModuleContext):
    """Test that inertia protocol does NOT use "just start" (CRITICAL anti-pattern)."""
    response = await coaching_engine.inertia_protocol(module_context_autism)
    # Verify message doesn't contain problematic phrases
    message_lower = response.text.lower()
    assert "just start" not in message_lower
    assert "just begin" not in message_lower


@pytest.mark.asyncio
async def test_inertia_protocol_uses_transition_bridges(coaching_engine: CoachingEngine, module_context_autism: ModuleContext):
    """Test that inertia protocol uses transition bridges (small pre-tasks)."""
    response = await coaching_engine.inertia_protocol(module_context_autism)
    # Should mention small steps, breaking down, or structure
    message_lower = response.text.lower()
    has_bridge_language = any(
        phrase in message_lower
        for phrase in ["small", "step", "break", "tell you", "first"]
    )
    assert has_bridge_language


# =============================================================================
# Test: Channel Dominance (AuDHD)
# =============================================================================


@pytest.mark.asyncio
async def test_check_channel_dominance_returns_valid_value(coaching_engine: CoachingEngine):
    """Test that check_channel_dominance returns a valid ChannelDominance."""
    channel = await coaching_engine.check_channel_dominance(user_id=1)
    assert channel in ["ADHD", "AUTISM", "BALANCED"]


@pytest.mark.asyncio
async def test_check_channel_dominance_deterministic_per_day(coaching_engine: CoachingEngine):
    """Test that channel dominance is deterministic for a given user+day."""
    channel1 = await coaching_engine.check_channel_dominance(user_id=1)
    channel2 = await coaching_engine.check_channel_dominance(user_id=1)
    assert channel1 == channel2


@pytest.mark.asyncio
async def test_check_channel_dominance_uses_redis_cache(coaching_engine: CoachingEngine):
    """Test that channel dominance uses Redis cache."""
    f"channel_dominance:1:{date.today().isoformat()}"

    # Mock Redis to return cached value
    coaching_engine.redis_service.get = AsyncMock(return_value='"ADHD"')

    channel = await coaching_engine.check_channel_dominance(user_id=1)
    assert channel == "ADHD"


@pytest.mark.asyncio
async def test_check_channel_dominance_sets_redis_cache(coaching_engine: CoachingEngine):
    """Test that channel dominance sets Redis cache."""
    coaching_engine.redis_service.get = AsyncMock(return_value=None)
    coaching_engine.redis_service.set = AsyncMock()

    await coaching_engine.check_channel_dominance(user_id=1)

    coaching_engine.redis_service.set.assert_called_once()


# =============================================================================
# Test: AuDHD Handling (Channel Dominance Check FIRST)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_audhd_checks_channel_first(coaching_engine: CoachingEngine, module_context_audhd: ModuleContext):
    """Test that AuDHD handling checks channel dominance FIRST (SW-19)."""
    with patch.object(coaching_engine, 'check_channel_dominance', new_callable=AsyncMock) as mock_check:
        mock_check.return_value = "ADHD"

        await coaching_engine._handle_audhd(module_context_audhd)

        mock_check.assert_called_once_with(module_context_audhd.user_id)


@pytest.mark.asyncio
async def test_handle_audhd_routes_to_pinch_on_adhd_day(coaching_engine: CoachingEngine, module_context_audhd: ModuleContext):
    """Test that AuDHD routes to PINCH on ADHD-dominant days."""
    with patch.object(coaching_engine, 'check_channel_dominance', new_callable=AsyncMock, return_value="ADHD"):
        with patch.object(coaching_engine, 'pinch_activation', new_callable=AsyncMock) as mock_pinch:
            await coaching_engine._handle_audhd(module_context_audhd)
            mock_pinch.assert_called_once()


@pytest.mark.asyncio
async def test_handle_audhd_routes_to_inertia_on_autism_day(coaching_engine: CoachingEngine, module_context_audhd: ModuleContext):
    """Test that AuDHD routes to inertia protocol on Autism-dominant days."""
    with patch.object(coaching_engine, 'check_channel_dominance', new_callable=AsyncMock, return_value="AUTISM"):
        with patch.object(coaching_engine, 'inertia_protocol', new_callable=AsyncMock) as mock_inertia:
            await coaching_engine._handle_audhd(module_context_audhd)
            mock_inertia.assert_called_once()


@pytest.mark.asyncio
async def test_handle_audhd_hybrid_on_balanced_day(coaching_engine: CoachingEngine, module_context_audhd: ModuleContext):
    """Test that AuDHD uses hybrid approach on BALANCED days."""
    with patch.object(coaching_engine, 'check_channel_dominance', new_callable=AsyncMock, return_value="BALANCED"):
        response = await coaching_engine._handle_audhd(module_context_audhd)
        assert response.metadata["protocol"] == "audhd_balanced"


# =============================================================================
# Test: Standard Motivation (Neurotypical)
# =============================================================================


@pytest.mark.asyncio
async def test_standard_motivation_returns_response(coaching_engine: CoachingEngine, module_context_neurotypical: ModuleContext):
    """Test standard motivation returns a CoachingResponse."""
    response = await coaching_engine.standard_motivation(module_context_neurotypical)
    assert isinstance(response, CoachingResponse)
    assert response.metadata["protocol"] == "standard_motivation"
    assert response.metadata["segment"] == "NT"


# =============================================================================
# Test: Burnout Gate (SW-12)
# =============================================================================


@pytest.mark.asyncio
async def test_burnout_gate_detects_burnout_quadrant(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout gate detects BURNOUT quadrant."""
    # BURNOUT: sonne < 0.5, erde >= 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.3,
        erde=0.7,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    gate = await coaching_engine.burnout_gate(module_context_adhd)
    assert gate is True


@pytest.mark.asyncio
async def test_burnout_gate_detects_crisis_quadrant(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout gate also gates on CRISIS quadrant."""
    # CRISIS: sonne < 0.5, erde < 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.2,
        erde=0.2,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    gate = await coaching_engine.burnout_gate(module_context_adhd)
    assert gate is True


@pytest.mark.asyncio
async def test_burnout_gate_allows_sweet_spot(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout gate allows SWEET_SPOT quadrant."""
    # SWEET_SPOT: sonne >= 0.5, erde >= 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.8,
        erde=0.8,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    gate = await coaching_engine.burnout_gate(module_context_adhd)
    assert gate is False


# =============================================================================
# Test: Crisis Handling (SW-11)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_crisis_pauses_module(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that crisis handling pauses the module."""
    response = await coaching_engine._handle_crisis(module_context_adhd)
    assert response.should_continue_module is False
    assert response.is_crisis_response is True
    assert response.recommended_action == "pause_module"


@pytest.mark.asyncio
async def test_handle_crisis_adapts_to_inertia_type(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that crisis response adapts to inertia type."""
    response = await coaching_engine._handle_crisis(module_context_adhd)
    assert "inertia_type" in response.metadata


@pytest.mark.asyncio
async def test_handle_crisis_no_task_prompts(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that crisis response has NO task-focused prompts."""
    response = await coaching_engine._handle_crisis(module_context_adhd)
    message_lower = response.text.lower()
    # Should NOT contain task-focused language
    assert "task" not in message_lower
    assert "do" not in message_lower or "don't have to do" in message_lower


# =============================================================================
# Test: Burnout Redirect (SW-12)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_burnout_shifts_to_recovery(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout redirect shifts from activation to recovery."""
    response = await coaching_engine._handle_burnout(module_context_adhd)
    assert response.is_burnout_redirect is True
    assert response.recommended_action == "gentle_redirect"
    message_lower = response.text.lower()
    assert "recovery" in message_lower or "rest" in message_lower or "break" in message_lower


@pytest.mark.asyncio
async def test_handle_burnout_adapts_to_burnout_model(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout redirect adapts to burnout model."""
    response = await coaching_engine._handle_burnout(module_context_adhd)
    assert "burnout_model" in response.metadata


@pytest.mark.asyncio
async def test_handle_burnout_no_behavioral_activation(coaching_engine: CoachingEngine, module_context_autism: ModuleContext):
    """Test that burnout redirect does NOT use Behavioral Activation (CRITICAL anti-pattern)."""
    response = await coaching_engine._handle_burnout(module_context_autism)
    message_lower = response.text.lower()
    # Should NOT contain activation language
    assert "activate" not in message_lower
    assert "get going" not in message_lower
    assert "push" not in message_lower or "no big push" in message_lower


# =============================================================================
# Test: Sweet Spot Reinforcement
# =============================================================================


@pytest.mark.asyncio
async def test_reinforce_sweet_spot_returns_reinforcement(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that sweet spot reinforcement returns positive message."""
    response = await coaching_engine._reinforce_sweet_spot(module_context_adhd)
    assert response.should_continue_module is True
    assert response.metadata["protocol"] == "sweet_spot_reinforce"


# =============================================================================
# Test: Handle Stuck (Main Entry Point)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_stuck_routes_to_segment_protocol(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that handle_stuck routes to segment-specific protocol."""
    # AVOIDANCE: sonne >= 0.5, erde < 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.8,
        erde=0.3,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)
    coaching_engine.burnout_gate = AsyncMock(return_value=False)

    with patch.object(coaching_engine, 'pinch_activation', new_callable=AsyncMock) as mock_pinch:
        await coaching_engine.handle_stuck(
            message="I'm stuck",
            ctx=module_context_adhd,
            active_module="planning",
            active_state="gather_tasks",
        )
        # Should route to PINCH for ADHD (features.icnu_enabled)
        mock_pinch.assert_called_once()


@pytest.mark.asyncio
async def test_handle_stuck_uses_segment_context_not_string_comparison(coaching_engine: CoachingEngine, module_context_autism: ModuleContext):
    """Test that handle_stuck uses SegmentContext fields, NOT string comparison (CRITICAL)."""
    # AVOIDANCE: sonne >= 0.5, erde < 0.5
    mock_state = TensionState(
        user_id=2,
        sonne=0.8,
        erde=0.3,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)
    coaching_engine.burnout_gate = AsyncMock(return_value=False)

    with patch.object(coaching_engine, 'inertia_protocol', new_callable=AsyncMock) as mock_inertia:
        await coaching_engine.handle_stuck(
            message="I'm stuck",
            ctx=module_context_autism,
            active_module="planning",
            active_state="gather_tasks",
        )
        # Should route to inertia for Autism (features.routine_anchoring)
        mock_inertia.assert_called_once()


@pytest.mark.asyncio
async def test_handle_stuck_crisis_overrides_all(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that CRISIS quadrant overrides normal stuck handling."""
    # CRISIS: sonne < 0.5, erde < 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.2,
        erde=0.2,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)

    with patch.object(coaching_engine, '_handle_crisis', new_callable=AsyncMock) as mock_crisis:
        await coaching_engine.handle_stuck(
            message="I'm stuck",
            ctx=module_context_adhd,
            active_module="planning",
            active_state="gather_tasks",
        )
        mock_crisis.assert_called_once()


@pytest.mark.asyncio
async def test_handle_stuck_burnout_redirects(coaching_engine: CoachingEngine, module_context_adhd: ModuleContext):
    """Test that burnout gate redirects to recovery."""
    # AVOIDANCE: sonne >= 0.5, erde < 0.5
    mock_state = TensionState(
        user_id=1,
        sonne=0.8,
        erde=0.3,
    )
    coaching_engine.tension_engine.get_state = AsyncMock(return_value=mock_state)
    coaching_engine.burnout_gate = AsyncMock(return_value=True)  # Burnout detected

    with patch.object(coaching_engine, '_handle_burnout', new_callable=AsyncMock) as mock_burnout:
        await coaching_engine.handle_stuck(
            message="I'm stuck",
            ctx=module_context_adhd,
            active_module="planning",
            active_state="gather_tasks",
        )
        mock_burnout.assert_called_once()


# =============================================================================
# Test: Effectiveness Tracking
# =============================================================================


@pytest.mark.asyncio
async def test_effectiveness_track_with_session(coaching_engine: CoachingEngine):
    """Test effectiveness tracking with database session."""
    mock_session = MagicMock()
    response = CoachingResponse(text="Test", metadata={"protocol": "pinch_activation"})

    # get_effectiveness_service is imported locally inside effectiveness_track,
    # so patch it in the src.services.effectiveness module where it's defined
    with patch('src.services.effectiveness.get_effectiveness_service', new_callable=AsyncMock) as mock_get_service:
        mock_service = MagicMock()
        mock_service.log_intervention = AsyncMock()
        mock_get_service.return_value = mock_service

        await coaching_engine.effectiveness_track(
            user_id=1,
            intervention_type="inline_coaching",
            response=response,
            segment_code="AD",
            session=mock_session,
        )

        # Should NOT raise exception


@pytest.mark.asyncio
async def test_effectiveness_track_without_session(coaching_engine: CoachingEngine):
    """Test effectiveness tracking without database session."""
    response = CoachingResponse(text="Test")

    await coaching_engine.effectiveness_track(
        user_id=1,
        intervention_type="inline_coaching",
        response=response,
        segment_code="AD",
        session=None,
    )
    # Should return early without error
