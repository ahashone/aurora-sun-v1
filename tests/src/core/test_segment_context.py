"""
Unit tests for SegmentContext and related configuration dataclasses.

Tests cover:
- SegmentContext.from_code() factory method for all 5 codes
- SegmentCore configuration per segment (max_priorities, sprint_minutes, etc.)
- SegmentUX configuration per segment
- NeurostateConfig per segment (burnout_model, inertia_type, masking_model, etc.)
- SegmentFeatures per segment (feature flags)
- Display name mapping (internal codes to user-facing names)
"""

import pytest

from src.core.segment_context import (
    SEGMENT_DISPLAY_NAMES,
    NeurostateConfig,
    SegmentContext,
    SegmentCore,
    SegmentFeatures,
    SegmentUX,
)

# =============================================================================
# TestFromCode -- SegmentContext.from_code() factory
# =============================================================================

class TestFromCode:
    """Test SegmentContext.from_code() for all 5 segment codes."""

    def test_ad_returns_context(self):
        """AD code returns a valid SegmentContext."""
        ctx = SegmentContext.from_code("AD")
        assert isinstance(ctx, SegmentContext)
        assert ctx.core.code == "AD"

    def test_au_returns_context(self):
        """AU code returns a valid SegmentContext."""
        ctx = SegmentContext.from_code("AU")
        assert isinstance(ctx, SegmentContext)
        assert ctx.core.code == "AU"

    def test_ah_returns_context(self):
        """AH code returns a valid SegmentContext."""
        ctx = SegmentContext.from_code("AH")
        assert isinstance(ctx, SegmentContext)
        assert ctx.core.code == "AH"

    def test_nt_returns_context(self):
        """NT code returns a valid SegmentContext."""
        ctx = SegmentContext.from_code("NT")
        assert isinstance(ctx, SegmentContext)
        assert ctx.core.code == "NT"

    def test_cu_returns_context(self):
        """CU code returns a valid SegmentContext."""
        ctx = SegmentContext.from_code("CU")
        assert isinstance(ctx, SegmentContext)
        assert ctx.core.code == "CU"

    def test_all_have_four_sub_objects(self):
        """Every code returns a context with all 4 sub-objects."""
        for code in ("AD", "AU", "AH", "NT", "CU"):
            ctx = SegmentContext.from_code(code)
            assert isinstance(ctx.core, SegmentCore)
            assert isinstance(ctx.ux, SegmentUX)
            assert isinstance(ctx.neuro, NeurostateConfig)
            assert isinstance(ctx.features, SegmentFeatures)

    def test_invalid_code_raises(self):
        """Invalid code raises KeyError."""
        with pytest.raises(KeyError):
            SegmentContext.from_code("XX")


# =============================================================================
# TestSegmentCoreAD
# =============================================================================

class TestSegmentCoreAD:
    """Test SegmentCore configuration for ADHD (AD)."""

    @pytest.fixture
    def core(self):
        return SegmentContext.from_code("AD").core

    def test_code(self, core):
        assert core.code == "AD"

    def test_display_name(self, core):
        assert core.display_name == "ADHD"

    def test_max_priorities(self, core):
        """AD has max_priorities=2 (fewer to avoid overwhelm)."""
        assert core.max_priorities == 2

    def test_sprint_minutes(self, core):
        """AD has sprint_minutes=25 (Pomodoro-like short sprints)."""
        assert core.sprint_minutes == 25

    def test_habit_threshold_days(self, core):
        """AD has habit_threshold_days=21."""
        assert core.habit_threshold_days == 21


# =============================================================================
# TestSegmentCoreAU
# =============================================================================

class TestSegmentCoreAU:
    """Test SegmentCore configuration for Autism (AU)."""

    @pytest.fixture
    def core(self):
        return SegmentContext.from_code("AU").core

    def test_code(self, core):
        assert core.code == "AU"

    def test_display_name(self, core):
        assert core.display_name == "Autism"

    def test_max_priorities(self, core):
        """AU has max_priorities=3."""
        assert core.max_priorities == 3

    def test_sprint_minutes(self, core):
        """AU has sprint_minutes=45 (longer for deep focus)."""
        assert core.sprint_minutes == 45

    def test_habit_threshold_days(self, core):
        """AU has habit_threshold_days=14 (quicker habit formation)."""
        assert core.habit_threshold_days == 14


# =============================================================================
# TestSegmentCoreAH
# =============================================================================

class TestSegmentCoreAH:
    """Test SegmentCore configuration for AuDHD (AH)."""

    @pytest.fixture
    def core(self):
        return SegmentContext.from_code("AH").core

    def test_code(self, core):
        assert core.code == "AH"

    def test_display_name(self, core):
        assert core.display_name == "AuDHD"

    def test_max_priorities(self, core):
        """AH has max_priorities=3."""
        assert core.max_priorities == 3

    def test_sprint_minutes(self, core):
        """AH has sprint_minutes=35 (between AD and AU)."""
        assert core.sprint_minutes == 35

    def test_habit_threshold_days(self, core):
        """AH has habit_threshold_days=21."""
        assert core.habit_threshold_days == 21


# =============================================================================
# TestSegmentCoreNT
# =============================================================================

class TestSegmentCoreNT:
    """Test SegmentCore configuration for Neurotypical (NT)."""

    @pytest.fixture
    def core(self):
        return SegmentContext.from_code("NT").core

    def test_code(self, core):
        assert core.code == "NT"

    def test_display_name(self, core):
        assert core.display_name == "Neurotypical"

    def test_max_priorities(self, core):
        """NT has max_priorities=3."""
        assert core.max_priorities == 3

    def test_sprint_minutes(self, core):
        """NT has sprint_minutes=40."""
        assert core.sprint_minutes == 40

    def test_habit_threshold_days(self, core):
        """NT has habit_threshold_days=21."""
        assert core.habit_threshold_days == 21


# =============================================================================
# TestSegmentCoreCU
# =============================================================================

class TestSegmentCoreCU:
    """Test SegmentCore configuration for Custom (CU)."""

    @pytest.fixture
    def core(self):
        return SegmentContext.from_code("CU").core

    def test_code(self, core):
        assert core.code == "CU"

    def test_display_name(self, core):
        assert core.display_name == "Custom"

    def test_max_priorities_same_as_nt(self, core):
        """CU defaults to NT values: max_priorities=3."""
        assert core.max_priorities == 3

    def test_sprint_minutes_same_as_nt(self, core):
        """CU defaults to NT values: sprint_minutes=40."""
        assert core.sprint_minutes == 40


# =============================================================================
# TestSegmentFeaturesAD
# =============================================================================

class TestSegmentFeaturesAD:
    """Test SegmentFeatures for ADHD (AD)."""

    @pytest.fixture
    def features(self):
        return SegmentContext.from_code("AD").features

    def test_icnu_enabled(self, features):
        """AD has ICNU enabled."""
        assert features.icnu_enabled is True

    def test_sensory_check_not_required(self, features):
        """AD does not require sensory check."""
        assert features.sensory_check_required is False

    def test_spoon_drawer_disabled(self, features):
        """AD does not have spoon drawer."""
        assert features.spoon_drawer_enabled is False

    def test_channel_dominance_disabled(self, features):
        """AD does not have channel dominance."""
        assert features.channel_dominance_enabled is False

    def test_routine_anchoring_disabled(self, features):
        """AD does not have routine anchoring."""
        assert features.routine_anchoring is False

    def test_integrity_trigger_disabled(self, features):
        """AD does not have integrity trigger."""
        assert features.integrity_trigger_enabled is False


# =============================================================================
# TestSegmentFeaturesAU
# =============================================================================

class TestSegmentFeaturesAU:
    """Test SegmentFeatures for Autism (AU)."""

    @pytest.fixture
    def features(self):
        return SegmentContext.from_code("AU").features

    def test_sensory_check_required(self, features):
        """AU requires sensory check."""
        assert features.sensory_check_required is True

    def test_routine_anchoring_enabled(self, features):
        """AU has routine anchoring enabled."""
        assert features.routine_anchoring is True

    def test_icnu_disabled(self, features):
        """AU does not have ICNU."""
        assert features.icnu_enabled is False

    def test_spoon_drawer_disabled(self, features):
        """AU does not have spoon drawer."""
        assert features.spoon_drawer_enabled is False

    def test_channel_dominance_disabled(self, features):
        """AU does not have channel dominance."""
        assert features.channel_dominance_enabled is False


# =============================================================================
# TestSegmentFeaturesAH
# =============================================================================

class TestSegmentFeaturesAH:
    """Test SegmentFeatures for AuDHD (AH)."""

    @pytest.fixture
    def features(self):
        return SegmentContext.from_code("AH").features

    def test_channel_dominance_enabled(self, features):
        """AH has channel dominance enabled."""
        assert features.channel_dominance_enabled is True

    def test_spoon_drawer_enabled(self, features):
        """AH has spoon drawer enabled."""
        assert features.spoon_drawer_enabled is True

    def test_icnu_enabled(self, features):
        """AH has ICNU enabled."""
        assert features.icnu_enabled is True

    def test_sensory_check_required(self, features):
        """AH requires sensory check."""
        assert features.sensory_check_required is True

    def test_integrity_trigger_enabled(self, features):
        """AH has integrity trigger enabled."""
        assert features.integrity_trigger_enabled is True

    def test_routine_anchoring_disabled(self, features):
        """AH does not have routine anchoring (that's AU-specific)."""
        assert features.routine_anchoring is False


# =============================================================================
# TestSegmentFeaturesNT
# =============================================================================

class TestSegmentFeaturesNT:
    """Test SegmentFeatures for Neurotypical (NT)."""

    @pytest.fixture
    def features(self):
        return SegmentContext.from_code("NT").features

    def test_no_special_features(self, features):
        """NT has no special features enabled."""
        assert features.icnu_enabled is False
        assert features.spoon_drawer_enabled is False
        assert features.channel_dominance_enabled is False
        assert features.integrity_trigger_enabled is False
        assert features.sensory_check_required is False
        assert features.routine_anchoring is False


# =============================================================================
# TestSegmentFeaturesCU
# =============================================================================

class TestSegmentFeaturesCU:
    """Test SegmentFeatures for Custom (CU) -- defaults to NT."""

    @pytest.fixture
    def features(self):
        return SegmentContext.from_code("CU").features

    def test_no_special_features(self, features):
        """CU defaults to NT: no special features enabled."""
        assert features.icnu_enabled is False
        assert features.spoon_drawer_enabled is False
        assert features.channel_dominance_enabled is False
        assert features.integrity_trigger_enabled is False
        assert features.sensory_check_required is False
        assert features.routine_anchoring is False


# =============================================================================
# TestNeurostateConfigAD
# =============================================================================

class TestNeurostateConfigAD:
    """Test NeurostateConfig for ADHD (AD)."""

    @pytest.fixture
    def neuro(self):
        return SegmentContext.from_code("AD").neuro

    def test_burnout_model(self, neuro):
        """AD uses boom_bust burnout model."""
        assert neuro.burnout_model == "boom_bust"

    def test_inertia_type(self, neuro):
        """AD uses activation_deficit inertia type."""
        assert neuro.inertia_type == "activation_deficit"

    def test_masking_model(self, neuro):
        """AD uses neurotypical masking model."""
        assert neuro.masking_model == "neurotypical"

    def test_energy_assessment(self, neuro):
        """AD uses self_report energy assessment."""
        assert neuro.energy_assessment == "self_report"

    def test_sensory_accumulation(self, neuro):
        """AD does not have sensory accumulation."""
        assert neuro.sensory_accumulation is False

    def test_interoception_reliability(self, neuro):
        """AD has moderate interoception reliability."""
        assert neuro.interoception_reliability == "moderate"


# =============================================================================
# TestNeurostateConfigAU
# =============================================================================

class TestNeurostateConfigAU:
    """Test NeurostateConfig for Autism (AU)."""

    @pytest.fixture
    def neuro(self):
        return SegmentContext.from_code("AU").neuro

    def test_burnout_model(self, neuro):
        """AU uses overload_shutdown burnout model."""
        assert neuro.burnout_model == "overload_shutdown"

    def test_inertia_type(self, neuro):
        """AU uses autistic_inertia type."""
        assert neuro.inertia_type == "autistic_inertia"

    def test_sensory_accumulation(self, neuro):
        """AU has sensory accumulation (no habituation)."""
        assert neuro.sensory_accumulation is True

    def test_masking_model(self, neuro):
        """AU uses social masking model."""
        assert neuro.masking_model == "social"

    def test_energy_assessment(self, neuro):
        """AU uses behavioral_proxy energy assessment."""
        assert neuro.energy_assessment == "behavioral_proxy"

    def test_interoception_reliability(self, neuro):
        """AU has low interoception reliability."""
        assert neuro.interoception_reliability == "low"


# =============================================================================
# TestNeurostateConfigAH
# =============================================================================

class TestNeurostateConfigAH:
    """Test NeurostateConfig for AuDHD (AH)."""

    @pytest.fixture
    def neuro(self):
        return SegmentContext.from_code("AH").neuro

    def test_burnout_model(self, neuro):
        """AH uses three_type burnout model."""
        assert neuro.burnout_model == "three_type"

    def test_masking_model(self, neuro):
        """AH uses double_exponential masking model."""
        assert neuro.masking_model == "double_exponential"

    def test_inertia_type(self, neuro):
        """AH uses double_block inertia type."""
        assert neuro.inertia_type == "double_block"

    def test_sensory_accumulation(self, neuro):
        """AH has sensory accumulation."""
        assert neuro.sensory_accumulation is True

    def test_energy_assessment(self, neuro):
        """AH uses composite energy assessment."""
        assert neuro.energy_assessment == "composite"

    def test_interoception_reliability(self, neuro):
        """AH has very_low interoception reliability."""
        assert neuro.interoception_reliability == "very_low"

    def test_waiting_mode_vulnerability(self, neuro):
        """AH has extreme waiting mode vulnerability."""
        assert neuro.waiting_mode_vulnerability == "extreme"


# =============================================================================
# TestNeurostateConfigNT
# =============================================================================

class TestNeurostateConfigNT:
    """Test NeurostateConfig for Neurotypical (NT)."""

    @pytest.fixture
    def neuro(self):
        return SegmentContext.from_code("NT").neuro

    def test_burnout_model(self, neuro):
        """NT uses standard burnout model."""
        assert neuro.burnout_model == "standard"

    def test_inertia_type(self, neuro):
        """NT has no inertia type."""
        assert neuro.inertia_type == "none"

    def test_sensory_accumulation(self, neuro):
        """NT does not have sensory accumulation."""
        assert neuro.sensory_accumulation is False

    def test_interoception_reliability(self, neuro):
        """NT has high interoception reliability."""
        assert neuro.interoception_reliability == "high"


# =============================================================================
# TestDisplayNames
# =============================================================================

class TestDisplayNames:
    """Test the SEGMENT_DISPLAY_NAMES mapping."""

    def test_ad_display_name(self):
        """AD maps to 'ADHD'."""
        assert SEGMENT_DISPLAY_NAMES["AD"] == "ADHD"

    def test_au_display_name(self):
        """AU maps to 'Autism'."""
        assert SEGMENT_DISPLAY_NAMES["AU"] == "Autism"

    def test_ah_display_name(self):
        """AH maps to 'AuDHD'."""
        assert SEGMENT_DISPLAY_NAMES["AH"] == "AuDHD"

    def test_nt_display_name(self):
        """NT maps to 'Neurotypical'."""
        assert SEGMENT_DISPLAY_NAMES["NT"] == "Neurotypical"

    def test_cu_display_name(self):
        """CU maps to 'Custom'."""
        assert SEGMENT_DISPLAY_NAMES["CU"] == "Custom"

    def test_display_name_matches_core(self):
        """Display names in mapping match SegmentCore.display_name."""
        for code in ("AD", "AU", "AH", "NT", "CU"):
            ctx = SegmentContext.from_code(code)
            assert ctx.core.display_name == SEGMENT_DISPLAY_NAMES[code]

    def test_five_segments_total(self):
        """There are exactly 5 segments defined."""
        assert len(SEGMENT_DISPLAY_NAMES) == 5


# =============================================================================
# TestSegmentUX
# =============================================================================

class TestSegmentUX:
    """Test SegmentUX configurations across segments."""

    def test_ad_energy_check_type(self):
        """AD uses simple energy check."""
        ctx = SegmentContext.from_code("AD")
        assert ctx.ux.energy_check_type == "simple"

    def test_au_energy_check_type(self):
        """AU uses sensory_cognitive energy check."""
        ctx = SegmentContext.from_code("AU")
        assert ctx.ux.energy_check_type == "sensory_cognitive"

    def test_ah_energy_check_type(self):
        """AH uses spoon_drawer energy check."""
        ctx = SegmentContext.from_code("AH")
        assert ctx.ux.energy_check_type == "spoon_drawer"

    def test_ad_gamification(self):
        """AD uses cumulative gamification."""
        ctx = SegmentContext.from_code("AD")
        assert ctx.ux.gamification == "cumulative"

    def test_au_gamification(self):
        """AU has no gamification."""
        ctx = SegmentContext.from_code("AU")
        assert ctx.ux.gamification == "none"

    def test_ah_gamification(self):
        """AH uses adaptive gamification."""
        ctx = SegmentContext.from_code("AH")
        assert ctx.ux.gamification == "adaptive"

    def test_ad_notification_strategy(self):
        """AD uses interval notification strategy."""
        ctx = SegmentContext.from_code("AD")
        assert ctx.ux.notification_strategy == "interval"

    def test_au_notification_strategy(self):
        """AU uses exact_time notification strategy."""
        ctx = SegmentContext.from_code("AU")
        assert ctx.ux.notification_strategy == "exact_time"

    def test_ah_notification_strategy(self):
        """AH uses semi_predictable notification strategy."""
        ctx = SegmentContext.from_code("AH")
        assert ctx.ux.notification_strategy == "semi_predictable"

    def test_nt_notification_strategy(self):
        """NT uses standard notification strategy."""
        ctx = SegmentContext.from_code("NT")
        assert ctx.ux.notification_strategy == "standard"

    def test_ad_money_steps(self):
        """AD has 3 money steps."""
        ctx = SegmentContext.from_code("AD")
        assert ctx.ux.money_steps == 3

    def test_au_money_steps(self):
        """AU has 7 money steps."""
        ctx = SegmentContext.from_code("AU")
        assert ctx.ux.money_steps == 7

    def test_ah_money_steps(self):
        """AH has 6 money steps."""
        ctx = SegmentContext.from_code("AH")
        assert ctx.ux.money_steps == 6

    def test_nt_money_steps(self):
        """NT has 4 money steps."""
        ctx = SegmentContext.from_code("NT")
        assert ctx.ux.money_steps == 4
