"""
Unit tests for the SensoryStateAssessment service.

Tests cover:
- Sensory load tracking (cumulative, not habituating for AU/AH)
- Modality-specific loads (visual, auditory, tactile, olfactory, proprioceptive)
- Overload detection thresholds
- Critical threshold detection
- Sensory profile creation/retrieval
- Update modality with cumulative delta
- Reset modality
- Recovery recommendations based on high modalities
- Overall load calculation (max of all modalities)
- Invalid modality validation
- Edge cases (zero load, max load, negative delta)

All DB dependencies use the shared db_session fixture with in-memory SQLite.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.services.neurostate.sensory import (
    ModalityInput,
    SensoryState,
    SensoryStateAssessment,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service(db_session):
    """Create a SensoryStateAssessment with a real in-memory DB session."""
    return SensoryStateAssessment(db=db_session)


@pytest.fixture
def mock_service():
    """Create a SensoryStateAssessment with a mock DB session."""
    mock_db = MagicMock()
    return SensoryStateAssessment(db=mock_db)


# =============================================================================
# TestModalities
# =============================================================================

class TestModalities:
    """Test the modality configuration."""

    def test_five_modalities(self, mock_service):
        """Service tracks 5 sensory modalities."""
        assert len(mock_service.MODALITIES) == 5

    def test_modality_names(self, mock_service):
        """Modality names are correct."""
        expected = ["visual", "auditory", "tactile", "olfactory", "proprioceptive"]
        assert mock_service.MODALITIES == expected


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

    def test_critical_higher_than_overload(self, mock_service):
        """Critical threshold is higher than overload threshold."""
        assert mock_service.CRITICAL_THRESHOLD > mock_service.OVERLOAD_THRESHOLD


# =============================================================================
# TestAssess
# =============================================================================

class TestAssess:
    """Test the assess() async method."""

    @pytest.mark.asyncio
    async def test_assess_returns_sensory_state(self, service):
        """assess() returns a SensoryState dataclass."""
        result = await service.assess(user_id=1)

        assert isinstance(result, SensoryState)
        assert result.user_id == 1
        assert isinstance(result.modality_loads, dict)
        assert isinstance(result.overall_load, float)
        assert isinstance(result.is_overloaded, bool)
        assert isinstance(result.is_critical, bool)

    @pytest.mark.asyncio
    async def test_assess_new_user_zero_loads(self, service):
        """New user starts with all modality loads at zero."""
        result = await service.assess(user_id=1)

        for mod in service.MODALITIES:
            assert result.modality_loads.get(mod, 0.0) == 0.0
        assert result.overall_load == 0.0

    @pytest.mark.asyncio
    async def test_assess_new_user_not_overloaded(self, service):
        """New user is not overloaded."""
        result = await service.assess(user_id=1)
        assert result.is_overloaded is False
        assert result.is_critical is False

    @pytest.mark.asyncio
    async def test_assess_with_custom_load(self, service):
        """Providing custom load dict overrides stored load."""
        custom_load = {
            "visual": 50.0,
            "auditory": 30.0,
            "tactile": 10.0,
            "olfactory": 5.0,
            "proprioceptive": 0.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)

        assert result.modality_loads["visual"] == 50.0
        assert result.modality_loads["auditory"] == 30.0

    @pytest.mark.asyncio
    async def test_assess_overall_load_is_max(self, service):
        """Overall load is the maximum across all modalities."""
        custom_load = {
            "visual": 60.0,
            "auditory": 85.0,
            "tactile": 40.0,
            "olfactory": 20.0,
            "proprioceptive": 10.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)

        assert result.overall_load == 85.0

    @pytest.mark.asyncio
    async def test_assess_overloaded_single_modality(self, service):
        """Overloaded when any single modality exceeds 80%."""
        custom_load = {
            "visual": 85.0,
            "auditory": 30.0,
            "tactile": 10.0,
            "olfactory": 5.0,
            "proprioceptive": 0.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)
        assert result.is_overloaded is True

    @pytest.mark.asyncio
    async def test_assess_not_overloaded_at_80(self, service):
        """80.0 exactly is NOT overloaded (threshold is >80)."""
        custom_load = {
            "visual": 80.0,
            "auditory": 30.0,
            "tactile": 10.0,
            "olfactory": 5.0,
            "proprioceptive": 0.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)
        assert result.is_overloaded is False

    @pytest.mark.asyncio
    async def test_assess_critical_single_modality(self, service):
        """Critical when any single modality exceeds 95%."""
        custom_load = {
            "visual": 30.0,
            "auditory": 96.0,
            "tactile": 10.0,
            "olfactory": 5.0,
            "proprioceptive": 0.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)
        assert result.is_critical is True
        assert result.is_overloaded is True  # Also overloaded

    @pytest.mark.asyncio
    async def test_assess_not_critical_at_95(self, service):
        """95.0 exactly is NOT critical (threshold is >95)."""
        custom_load = {
            "visual": 95.0,
            "auditory": 30.0,
            "tactile": 10.0,
            "olfactory": 5.0,
            "proprioceptive": 0.0,
        }
        result = await service.assess(user_id=1, current_load=custom_load)
        assert result.is_critical is False

    @pytest.mark.asyncio
    async def test_assess_default_segment_is_au(self, service):
        """Default segment code for new profiles is AU."""
        result = await service.assess(user_id=1)
        assert result.segment_code == "AU"

    @pytest.mark.asyncio
    async def test_assess_empty_load_dict(self, service):
        """Empty custom load dict produces 0 overall load."""
        result = await service.assess(user_id=1, current_load={})
        assert result.overall_load == 0.0
        assert result.is_overloaded is False
        assert result.is_critical is False


# =============================================================================
# TestUpdateModality
# =============================================================================

class TestUpdateModality:
    """Test the update_modality() async method."""

    @pytest.mark.asyncio
    async def test_increase_modality_load(self, service):
        """Positive delta increases modality load."""
        result = await service.update_modality(
            user_id=1, modality="visual", load_delta=30.0, context="bright screen"
        )
        assert result.modality_loads["visual"] == 30.0

    @pytest.mark.asyncio
    async def test_cumulative_load_increases(self, service):
        """Multiple updates accumulate cumulatively."""
        await service.update_modality(
            user_id=1, modality="auditory", load_delta=20.0, context="loud noise"
        )
        result = await service.update_modality(
            user_id=1, modality="auditory", load_delta=25.0, context="more noise"
        )
        assert result.modality_loads["auditory"] == 45.0

    @pytest.mark.asyncio
    async def test_negative_delta_reduces_load(self, service):
        """Negative delta reduces modality load."""
        await service.update_modality(
            user_id=1, modality="tactile", load_delta=50.0, context="clothing"
        )
        result = await service.update_modality(
            user_id=1, modality="tactile", load_delta=-20.0, context="changed clothes"
        )
        assert result.modality_loads["tactile"] == 30.0

    @pytest.mark.asyncio
    async def test_load_capped_at_100(self, service):
        """Modality load cannot exceed 100."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=80.0, context="test"
        )
        result = await service.update_modality(
            user_id=1, modality="visual", load_delta=50.0, context="test"
        )
        assert result.modality_loads["visual"] == 100.0

    @pytest.mark.asyncio
    async def test_load_floored_at_0(self, service):
        """Modality load cannot go below 0."""
        result = await service.update_modality(
            user_id=1, modality="visual", load_delta=-50.0, context="test"
        )
        assert result.modality_loads["visual"] == 0.0

    @pytest.mark.asyncio
    async def test_invalid_modality_raises_error(self, service):
        """Invalid modality name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid modality"):
            await service.update_modality(
                user_id=1, modality="emotional", load_delta=10.0, context="test"
            )

    @pytest.mark.asyncio
    async def test_update_individual_modalities_independent(self, service):
        """Updating one modality does not affect others."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=50.0, context="test"
        )
        await service.update_modality(
            user_id=1, modality="auditory", load_delta=30.0, context="test"
        )
        result = await service.assess(user_id=1)

        assert result.modality_loads["visual"] == 50.0
        assert result.modality_loads["auditory"] == 30.0
        assert result.modality_loads["tactile"] == 0.0

    @pytest.mark.asyncio
    async def test_update_triggers_overload_detection(self, service):
        """Update that pushes modality above 80 triggers overload."""
        result = await service.update_modality(
            user_id=1, modality="auditory", load_delta=85.0, context="concert"
        )
        assert result.is_overloaded is True


# =============================================================================
# TestResetModality
# =============================================================================

class TestResetModality:
    """Test the reset_modality() async method."""

    @pytest.mark.asyncio
    async def test_reset_brings_to_zero(self, service):
        """Reset reduces modality load to zero."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=75.0, context="test"
        )
        result = await service.reset_modality(user_id=1, modality="visual")
        assert result.modality_loads["visual"] == 0.0

    @pytest.mark.asyncio
    async def test_reset_does_not_affect_others(self, service):
        """Resetting one modality does not affect other modalities."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=50.0, context="test"
        )
        await service.update_modality(
            user_id=1, modality="auditory", load_delta=60.0, context="test"
        )
        result = await service.reset_modality(user_id=1, modality="visual")

        assert result.modality_loads["visual"] == 0.0
        assert result.modality_loads["auditory"] == 60.0

    @pytest.mark.asyncio
    async def test_reset_already_zero(self, service):
        """Resetting a modality already at zero remains at zero."""
        result = await service.reset_modality(user_id=1, modality="tactile")
        assert result.modality_loads["tactile"] == 0.0


# =============================================================================
# TestGetRecoveryRecommendations
# =============================================================================

class TestGetRecoveryRecommendations:
    """Test the get_recovery_recommendations() async method."""

    @pytest.mark.asyncio
    async def test_no_overload_manageable(self, service):
        """No overloaded modalities returns manageable message."""
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("manageable" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_visual_overload_recommendation(self, service):
        """Visual overload includes dim lights recommendation."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("visual" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_auditory_overload_recommendation(self, service):
        """Auditory overload includes earplugs recommendation."""
        await service.update_modality(
            user_id=1, modality="auditory", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("auditor" in r.lower() or "earplugs" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_tactile_overload_recommendation(self, service):
        """Tactile overload includes clothing recommendation."""
        await service.update_modality(
            user_id=1, modality="tactile", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("tactile" in r.lower() or "clothing" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_olfactory_overload_recommendation(self, service):
        """Olfactory overload includes environment recommendation."""
        await service.update_modality(
            user_id=1, modality="olfactory", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("olfactor" in r.lower() or "unscented" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_proprioceptive_overload_recommendation(self, service):
        """Proprioceptive overload includes grounding recommendation."""
        await service.update_modality(
            user_id=1, modality="proprioceptive", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert any("ground" in r.lower() or "weighted" in r.lower() for r in recs)

    @pytest.mark.asyncio
    async def test_multiple_overloads_multiple_recommendations(self, service):
        """Multiple overloaded modalities produce multiple recommendations."""
        await service.update_modality(
            user_id=1, modality="visual", load_delta=85.0, context="test"
        )
        await service.update_modality(
            user_id=1, modality="auditory", load_delta=85.0, context="test"
        )
        recs = await service.get_recovery_recommendations(user_id=1)
        assert len(recs) >= 2


# =============================================================================
# TestSensoryStateDataclass
# =============================================================================

class TestSensoryStateDataclass:
    """Test the SensoryState dataclass."""

    def test_sensory_state_construction(self):
        """SensoryState can be constructed with all fields."""
        state = SensoryState(
            user_id=1,
            modality_loads={"visual": 50.0, "auditory": 30.0},
            overall_load=50.0,
            last_assessed=datetime.now(UTC),
            segment_code="AU",
            is_overloaded=False,
            is_critical=False,
        )
        assert state.user_id == 1
        assert state.modality_loads["visual"] == 50.0
        assert state.overall_load == 50.0
        assert state.segment_code == "AU"


# =============================================================================
# TestModalityInputDataclass
# =============================================================================

class TestModalityInputDataclass:
    """Test the ModalityInput dataclass."""

    def test_modality_input_construction(self):
        """ModalityInput can be constructed with all fields."""
        input_data = ModalityInput(
            modality="visual",
            load_delta=15.0,
            context="bright lights",
        )
        assert input_data.modality == "visual"
        assert input_data.load_delta == 15.0
        assert input_data.context == "bright lights"
