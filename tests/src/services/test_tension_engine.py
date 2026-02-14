"""
Comprehensive tests for the TensionEngine (Sonne vs Erde quadrant mapping).

Tests cover:
- Quadrant enum (SWEET_SPOT, AVOIDANCE, BURNOUT, CRISIS)
- OverrideLevel hierarchy (SAFETY, GROUNDING, ALIGNMENT, OPTIMIZATION)
- FulfillmentType (GENUINE, PSEUDO, DUTY)
- TensionState class (sonne/erde levels, quadrant calculation, properties)
- TensionState.quadrant property (4 quadrant mapping)
- TensionState.needs_activation (activation vs recovery)
- TensionState.needs_recovery (burnout/crisis detection)
- TensionState.is_crisis (crisis state check)
- TensionState.to_dict (serialization)
- TensionEngine.get_state (fetch tension state, Redis-backed)
- TensionEngine.update_state (update sonne/erde, persist to Redis)
- TensionEngine.determine_override_level (safety hierarchy)
- TensionEngine.should_activate (activation gating by burnout)
- TensionEngine.detect_quadrant_shift (state change detection)
- TensionEngine.determine_fulfillment_type (genuine vs pseudo vs duty)
- Singleton access (get_tension_engine, get_user_tension)
- Redis persistence (state storage with 24h TTL)

Reference: ARCHITECTURE.md Section 4 (Tension Engine + Fulfillment)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.tension_engine import (
    Quadrant,
    TensionEngine,
    TensionState,
    get_tension_engine,
    get_user_tension,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis service."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def tension_engine(mock_redis):
    """Create a TensionEngine with mocked Redis."""
    # get_redis_service is imported locally inside TensionEngine.__init__,
    # so patch it at the source module
    with patch("src.services.redis_service.get_redis_service", return_value=mock_redis):
        engine = TensionEngine()
    return engine


# =============================================================================
# Quadrant Enum Tests
# =============================================================================


def test_quadrant_enum():
    """Test Quadrant enum values."""
    assert Quadrant.SWEET_SPOT.value == "SWEET_SPOT"
    assert Quadrant.AVOIDANCE.value == "AVOIDANCE"
    assert Quadrant.BURNOUT.value == "BURNOUT"
    assert Quadrant.CRISIS.value == "CRISIS"


# =============================================================================
# Override Hierarchy Tests
# =============================================================================


def test_override_hierarchy_order():
    """Test OVERRIDE_HIERARCHY is correctly ordered."""
    from src.services.tension_engine import OVERRIDE_HIERARCHY

    assert OVERRIDE_HIERARCHY[0] == "SAFETY"
    assert OVERRIDE_HIERARCHY[1] == "GROUNDING"
    assert OVERRIDE_HIERARCHY[2] == "ALIGNMENT"
    assert OVERRIDE_HIERARCHY[3] == "OPTIMIZATION"


# =============================================================================
# TensionState Tests
# =============================================================================


def test_tension_state_initialization():
    """Test TensionState initialization."""
    state = TensionState(sonne=0.8, erde=0.6, user_id=1)
    assert state.sonne == 0.8
    assert state.erde == 0.6
    assert state.user_id == 1


def test_tension_state_bounds_clamping():
    """Test TensionState clamps sonne/erde to [0, 1]."""
    # Above 1.0
    state1 = TensionState(sonne=1.5, erde=0.5, user_id=1)
    assert state1.sonne == 1.0

    # Below 0.0
    state2 = TensionState(sonne=0.5, erde=-0.5, user_id=1)
    assert state2.erde == 0.0


def test_tension_state_quadrant_sweet_spot():
    """Test quadrant = SWEET_SPOT when both sonne and erde >= 0.5."""
    state = TensionState(sonne=0.8, erde=0.7, user_id=1)
    assert state.quadrant == Quadrant.SWEET_SPOT


def test_tension_state_quadrant_avoidance():
    """Test quadrant = AVOIDANCE when sonne >= 0.5 and erde < 0.5."""
    state = TensionState(sonne=0.8, erde=0.3, user_id=1)
    assert state.quadrant == Quadrant.AVOIDANCE


def test_tension_state_quadrant_burnout():
    """Test quadrant = BURNOUT when sonne < 0.5 and erde >= 0.5."""
    state = TensionState(sonne=0.3, erde=0.7, user_id=1)
    assert state.quadrant == Quadrant.BURNOUT


def test_tension_state_quadrant_crisis():
    """Test quadrant = CRISIS when both sonne and erde < 0.5."""
    state = TensionState(sonne=0.2, erde=0.3, user_id=1)
    assert state.quadrant == Quadrant.CRISIS


def test_tension_state_needs_activation():
    """Test needs_activation returns True for SWEET_SPOT and AVOIDANCE."""
    sweet_spot = TensionState(sonne=0.8, erde=0.7, user_id=1)
    assert sweet_spot.needs_activation() is True

    avoidance = TensionState(sonne=0.8, erde=0.3, user_id=1)
    assert avoidance.needs_activation() is True

    burnout = TensionState(sonne=0.3, erde=0.7, user_id=1)
    assert burnout.needs_activation() is False


def test_tension_state_needs_recovery():
    """Test needs_recovery returns True for BURNOUT and CRISIS."""
    burnout = TensionState(sonne=0.3, erde=0.7, user_id=1)
    assert burnout.needs_recovery() is True

    crisis = TensionState(sonne=0.2, erde=0.3, user_id=1)
    assert crisis.needs_recovery() is True

    sweet_spot = TensionState(sonne=0.8, erde=0.7, user_id=1)
    assert sweet_spot.needs_recovery() is False


def test_tension_state_is_crisis():
    """Test is_crisis returns True only for CRISIS quadrant."""
    crisis = TensionState(sonne=0.2, erde=0.3, user_id=1)
    assert crisis.is_crisis() is True

    burnout = TensionState(sonne=0.3, erde=0.7, user_id=1)
    assert burnout.is_crisis() is False


def test_tension_state_to_dict():
    """Test TensionState serialization."""
    state = TensionState(sonne=0.8, erde=0.6, user_id=42)
    result = state.to_dict()

    assert result["user_id"] == 42
    assert result["sonne"] == 0.8
    assert result["erde"] == 0.6
    assert result["quadrant"] == "SWEET_SPOT"


# =============================================================================
# TensionEngine.get_state Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_state_default(tension_engine, mock_redis):
    """Test get_state returns default state for new user."""
    state = await tension_engine.get_state(user_id=1)

    assert state.sonne == 0.5
    assert state.erde == 0.5
    assert state.user_id == 1


@pytest.mark.asyncio
async def test_get_state_from_redis(tension_engine, mock_redis):
    """Test get_state loads from Redis."""
    # Mock Redis data
    redis_data = json.dumps({"sonne": 0.8, "erde": 0.6})
    mock_redis.get.return_value = redis_data

    state = await tension_engine.get_state(user_id=1)

    assert state.sonne == 0.8
    assert state.erde == 0.6


@pytest.mark.asyncio
async def test_get_state_caches_in_memory(tension_engine, mock_redis):
    """Test get_state caches in _states dict."""
    await tension_engine.get_state(user_id=1)

    # Second call should use in-memory cache, not Redis
    mock_redis.get.reset_mock()
    state2 = await tension_engine.get_state(user_id=1)

    mock_redis.get.assert_not_called()
    assert state2.user_id == 1


@pytest.mark.asyncio
async def test_get_state_handles_invalid_redis_data(tension_engine, mock_redis):
    """Test get_state falls back to default on invalid Redis data."""
    # Invalid JSON
    mock_redis.get.return_value = "invalid json"

    state = await tension_engine.get_state(user_id=1)

    # Should fall back to default
    assert state.sonne == 0.5
    assert state.erde == 0.5


# =============================================================================
# TensionEngine.update_state Tests
# =============================================================================


@pytest.mark.asyncio
async def test_update_state_updates_sonne(tension_engine, mock_redis):
    """Test update_state updates sonne value."""
    state = await tension_engine.update_state(user_id=1, sonne=0.9)

    assert state.sonne == 0.9
    assert state.erde == 0.5  # Default


@pytest.mark.asyncio
async def test_update_state_updates_erde(tension_engine, mock_redis):
    """Test update_state updates erde value."""
    state = await tension_engine.update_state(user_id=1, erde=0.7)

    assert state.sonne == 0.5  # Default
    assert state.erde == 0.7


@pytest.mark.asyncio
async def test_update_state_persists_to_redis(tension_engine, mock_redis):
    """Test update_state persists to Redis with 24h TTL."""
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.6)

    # Verify Redis set was called
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "tension:1"  # Key
    assert call_args[1]["ttl"] == 86400    # 24 hours


@pytest.mark.asyncio
async def test_update_state_preserves_existing_values(tension_engine, mock_redis):
    """Test update_state preserves values when None passed."""
    # Initialize
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.6)

    # Update only sonne
    state = await tension_engine.update_state(user_id=1, sonne=0.9)

    assert state.sonne == 0.9
    assert state.erde == 0.6  # Preserved


# =============================================================================
# TensionEngine.determine_override_level Tests
# =============================================================================


@pytest.mark.asyncio
async def test_determine_override_level_crisis(tension_engine, mock_redis):
    """Test determine_override_level returns SAFETY for crisis."""
    override = await tension_engine.determine_override_level(
        user_id=1,
        crisis_detected=True,
    )

    assert override == "SAFETY"


@pytest.mark.asyncio
async def test_determine_override_level_burnout(tension_engine, mock_redis):
    """Test determine_override_level returns SAFETY for high burnout."""
    override = await tension_engine.determine_override_level(
        user_id=1,
        burnout_severity=0.8,
    )

    assert override == "SAFETY"


@pytest.mark.asyncio
async def test_determine_override_level_low_grounding(tension_engine, mock_redis):
    """Test determine_override_level returns GROUNDING for low erde."""
    await tension_engine.update_state(user_id=1, sonne=0.5, erde=0.2)

    override = await tension_engine.determine_override_level(user_id=1)

    assert override == "GROUNDING"


@pytest.mark.asyncio
async def test_determine_override_level_low_fulfillment(tension_engine, mock_redis):
    """Test determine_override_level returns ALIGNMENT for low sonne."""
    await tension_engine.update_state(user_id=1, sonne=0.2, erde=0.5)

    override = await tension_engine.determine_override_level(user_id=1)

    assert override == "ALIGNMENT"


@pytest.mark.asyncio
async def test_determine_override_level_optimization(tension_engine, mock_redis):
    """Test determine_override_level returns OPTIMIZATION for good state."""
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.7)

    override = await tension_engine.determine_override_level(user_id=1)

    assert override == "OPTIMIZATION"


# =============================================================================
# TensionEngine.should_activate Tests
# =============================================================================


@pytest.mark.asyncio
async def test_should_activate_blocks_on_burnout(tension_engine, mock_redis):
    """Test should_activate returns False when burnout severity high."""
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.7)

    should_activate = await tension_engine.should_activate(user_id=1, burnout_severity=0.5)

    assert should_activate is False


@pytest.mark.asyncio
async def test_should_activate_allows_when_no_burnout(tension_engine, mock_redis):
    """Test should_activate returns True when no burnout and in activation quadrants."""
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.7)

    should_activate = await tension_engine.should_activate(user_id=1, burnout_severity=0.1)

    assert should_activate is True


@pytest.mark.asyncio
async def test_should_activate_blocks_in_recovery_quadrants(tension_engine, mock_redis):
    """Test should_activate returns False in BURNOUT/CRISIS quadrants."""
    await tension_engine.update_state(user_id=1, sonne=0.2, erde=0.3)  # CRISIS

    should_activate = await tension_engine.should_activate(user_id=1, burnout_severity=0.1)

    assert should_activate is False


# =============================================================================
# TensionEngine.detect_quadrant_shift Tests
# =============================================================================


@pytest.mark.asyncio
async def test_detect_quadrant_shift_no_change(tension_engine, mock_redis):
    """Test detect_quadrant_shift returns None when no change."""
    await tension_engine.update_state(user_id=1, sonne=0.8, erde=0.7)

    shift = await tension_engine.detect_quadrant_shift(user_id=1, previous_quadrant=Quadrant.SWEET_SPOT)

    assert shift is None


@pytest.mark.asyncio
async def test_detect_quadrant_shift_detects_change(tension_engine, mock_redis):
    """Test detect_quadrant_shift returns new quadrant on change."""
    await tension_engine.update_state(user_id=1, sonne=0.2, erde=0.3)  # CRISIS

    shift = await tension_engine.detect_quadrant_shift(user_id=1, previous_quadrant=Quadrant.SWEET_SPOT)

    assert shift == Quadrant.CRISIS


# =============================================================================
# TensionEngine.determine_fulfillment_type Tests
# =============================================================================


def test_determine_fulfillment_type_genuine(tension_engine):
    """Test determine_fulfillment_type returns GENUINE for activity + energy rise + results."""
    fulfillment_type = tension_engine.determine_fulfillment_type(
        activity_level=0.7,
        energy_change=0.3,
        results_achieved=True,
    )

    assert fulfillment_type == "GENUINE"


def test_determine_fulfillment_type_pseudo(tension_engine):
    """Test determine_fulfillment_type returns PSEUDO for activity + no results."""
    fulfillment_type = tension_engine.determine_fulfillment_type(
        activity_level=0.7,
        energy_change=0.2,
        results_achieved=False,
    )

    assert fulfillment_type == "PSEUDO"


def test_determine_fulfillment_type_duty(tension_engine):
    """Test determine_fulfillment_type returns DUTY for results + energy drain."""
    fulfillment_type = tension_engine.determine_fulfillment_type(
        activity_level=0.6,
        energy_change=-0.5,
        results_achieved=True,
    )

    assert fulfillment_type == "DUTY"


# =============================================================================
# Singleton Tests
# =============================================================================


def test_get_tension_engine_singleton():
    """Test get_tension_engine returns singleton instance."""
    engine1 = get_tension_engine()
    engine2 = get_tension_engine()
    assert engine1 is engine2


@pytest.mark.asyncio
async def test_get_user_tension_convenience():
    """Test get_user_tension convenience function."""
    state = await get_user_tension(user_id=1)
    assert isinstance(state, TensionState)


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_update_state_boundary_values(tension_engine, mock_redis):
    """Test update_state handles exact boundary values (0.5)."""
    # Exactly 0.5, 0.5 → SWEET_SPOT
    state1 = await tension_engine.update_state(user_id=1, sonne=0.5, erde=0.5)
    assert state1.quadrant == Quadrant.SWEET_SPOT

    # Exactly 0.5, 0.49 → AVOIDANCE
    state2 = await tension_engine.update_state(user_id=2, sonne=0.5, erde=0.49)
    assert state2.quadrant == Quadrant.AVOIDANCE


@pytest.mark.asyncio
async def test_get_state_concurrent_access(tension_engine, mock_redis):
    """Test get_state handles concurrent access correctly."""
    # First access
    state1 = await tension_engine.get_state(user_id=1)

    # Simulate external update (bypass in-memory cache)
    redis_data = json.dumps({"sonne": 0.9, "erde": 0.8})
    mock_redis.get.return_value = redis_data

    # Second access should use in-memory cache
    state2 = await tension_engine.get_state(user_id=1)

    # Should be same as state1 (in-memory cache)
    assert state2.sonne == state1.sonne


@pytest.mark.asyncio
async def test_update_state_extreme_values(tension_engine, mock_redis):
    """Test update_state handles extreme values."""
    # Far above 1.0
    state = await tension_engine.update_state(user_id=1, sonne=999.0, erde=-999.0)

    assert state.sonne == 1.0
    assert state.erde == 0.0
