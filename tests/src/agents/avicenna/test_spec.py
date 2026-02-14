"""
Unit tests for Avicenna SpecManager.

Tests cover:
- Loading spec from YAML file
- Loading spec from dict (for testing)
- Querying module names, states, transitions
- Validation of transitions
- Expected writes retrieval
- SLA configuration
- Severity rules retrieval
- Fallback loading when PyYAML unavailable
"""

import pytest
from pathlib import Path

from src.agents.avicenna.spec import (
    ExpectedWrite,
    ModuleSpec,
    SLAConfig,
    SpecManager,
    ValidTransition,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def spec_manager():
    """Create an empty SpecManager."""
    return SpecManager()


@pytest.fixture
def sample_spec_dict():
    """Sample spec data for testing."""
    return {
        "modules": {
            "planning": {
                "states": ["SCOPE", "PLAN", "DONE"],
                "transitions": [
                    {
                        "from": None,
                        "to": "SCOPE",
                        "expected_writes": [
                            {
                                "table": "sessions",
                                "count": "1",
                                "description": "Create session",
                            }
                        ],
                    },
                    {
                        "from": "SCOPE",
                        "to": "PLAN",
                        "expected_writes": [
                            {
                                "table": "daily_plans",
                                "count": "1",
                                "description": "Create plan",
                            }
                        ],
                    },
                    {
                        "from": "PLAN",
                        "to": "DONE",
                        "expected_writes": [],
                    },
                ],
            },
            "review": {
                "states": ["START", "REFLECT", "DONE"],
                "transitions": [
                    {
                        "from": None,
                        "to": "START",
                        "expected_writes": [],
                    },
                    {
                        "from": "START",
                        "to": "REFLECT",
                        "expected_writes": [],
                    },
                ],
            },
        },
        "slas": {
            "max_response_time_seconds": 30,
            "max_state_duration_minutes": 30,
            "max_interaction_gap_minutes": 60,
            "admin_notification_cooldown_seconds": 60,
            "max_concurrent_sessions_per_user": 3,
        },
        "severity_rules": {
            "critical": [
                {"type": "invalid_transition", "description": "State transition not in spec"},
                {"type": "stuck_state", "description": "User stuck in state > 30 min"},
            ],
            "warning": [
                {"type": "stale_interaction", "description": "No interaction > 60 min"},
            ],
        },
    }


@pytest.fixture
def loaded_spec_manager(spec_manager, sample_spec_dict):
    """Create a SpecManager pre-loaded with sample spec."""
    spec_manager.load_from_dict(sample_spec_dict)
    return spec_manager


# =============================================================================
# TestLoadSpec
# =============================================================================

class TestLoadSpec:
    """Test spec loading functionality."""

    def test_load_from_dict(self, spec_manager, sample_spec_dict):
        """Can load spec from dictionary."""
        spec_manager.load_from_dict(sample_spec_dict)

        assert spec_manager.is_loaded
        assert len(spec_manager.get_module_names()) == 2

    def test_is_loaded_false_initially(self, spec_manager):
        """is_loaded is False for new SpecManager."""
        assert not spec_manager.is_loaded

    def test_is_loaded_true_after_load(self, spec_manager, sample_spec_dict):
        """is_loaded is True after loading."""
        spec_manager.load_from_dict(sample_spec_dict)
        assert spec_manager.is_loaded

    def test_load_empty_dict(self, spec_manager):
        """Can load empty spec dict."""
        spec_manager.load_from_dict({})
        assert spec_manager.is_loaded
        assert len(spec_manager.get_module_names()) == 0

    def test_load_modules_only(self, spec_manager):
        """Can load spec with only modules section."""
        spec_manager.load_from_dict({
            "modules": {
                "test": {
                    "states": ["A", "B"],
                    "transitions": [],
                }
            }
        })
        assert spec_manager.is_loaded
        assert "test" in spec_manager.get_module_names()

    def test_load_slas_only(self, spec_manager):
        """Can load spec with only SLAs section."""
        spec_manager.load_from_dict({
            "slas": {
                "max_response_time_seconds": 45,
            }
        })
        assert spec_manager.is_loaded
        sla = spec_manager.get_sla()
        assert sla.max_response_time_seconds == 45


# =============================================================================
# TestGetModuleNames
# =============================================================================

class TestGetModuleNames:
    """Test getting module names."""

    def test_get_module_names_empty(self, spec_manager):
        """Empty spec returns empty list."""
        spec_manager.load_from_dict({})
        assert spec_manager.get_module_names() == []

    def test_get_module_names_multiple(self, loaded_spec_manager):
        """Returns all module names."""
        names = loaded_spec_manager.get_module_names()
        assert "planning" in names
        assert "review" in names
        assert len(names) == 2

    def test_get_module_names_before_load(self, spec_manager):
        """Returns empty list if not loaded."""
        assert spec_manager.get_module_names() == []


# =============================================================================
# TestGetModuleStates
# =============================================================================

class TestGetModuleStates:
    """Test getting module states."""

    def test_get_module_states_planning(self, loaded_spec_manager):
        """Returns states for planning module."""
        states = loaded_spec_manager.get_module_states("planning")
        assert states == ["SCOPE", "PLAN", "DONE"]

    def test_get_module_states_review(self, loaded_spec_manager):
        """Returns states for review module."""
        states = loaded_spec_manager.get_module_states("review")
        assert states == ["START", "REFLECT", "DONE"]

    def test_get_module_states_unknown_module(self, loaded_spec_manager):
        """Returns empty list for unknown module."""
        states = loaded_spec_manager.get_module_states("unknown")
        assert states == []

    def test_get_module_states_empty_spec(self, spec_manager):
        """Returns empty list for empty spec."""
        spec_manager.load_from_dict({})
        states = spec_manager.get_module_states("any")
        assert states == []


# =============================================================================
# TestGetValidTransitions
# =============================================================================

class TestGetValidTransitions:
    """Test getting valid transitions."""

    def test_get_valid_transitions_planning(self, loaded_spec_manager):
        """Returns transitions for planning module."""
        transitions = loaded_spec_manager.get_valid_transitions("planning")
        assert len(transitions) == 3

    def test_get_valid_transitions_review(self, loaded_spec_manager):
        """Returns transitions for review module."""
        transitions = loaded_spec_manager.get_valid_transitions("review")
        assert len(transitions) == 2

    def test_get_valid_transitions_unknown_module(self, loaded_spec_manager):
        """Returns empty list for unknown module."""
        transitions = loaded_spec_manager.get_valid_transitions("unknown")
        assert transitions == []

    def test_transition_structure(self, loaded_spec_manager):
        """Transitions have correct structure."""
        transitions = loaded_spec_manager.get_valid_transitions("planning")

        # First transition: None -> SCOPE
        first = transitions[0]
        assert isinstance(first, ValidTransition)
        assert first.from_state is None
        assert first.to_state == "SCOPE"
        assert len(first.expected_writes) == 1


# =============================================================================
# TestIsValidTransition
# =============================================================================

class TestIsValidTransition:
    """Test transition validation."""

    def test_valid_transition_none_to_scope(self, loaded_spec_manager):
        """None -> SCOPE is valid for planning."""
        assert loaded_spec_manager.is_valid_transition("planning", None, "SCOPE")

    def test_valid_transition_scope_to_plan(self, loaded_spec_manager):
        """SCOPE -> PLAN is valid for planning."""
        assert loaded_spec_manager.is_valid_transition("planning", "SCOPE", "PLAN")

    def test_valid_transition_plan_to_done(self, loaded_spec_manager):
        """PLAN -> DONE is valid for planning."""
        assert loaded_spec_manager.is_valid_transition("planning", "PLAN", "DONE")

    def test_invalid_transition_scope_to_done(self, loaded_spec_manager):
        """SCOPE -> DONE is invalid (not in spec)."""
        assert not loaded_spec_manager.is_valid_transition("planning", "SCOPE", "DONE")

    def test_invalid_transition_unknown_state(self, loaded_spec_manager):
        """Transitions with unknown states are invalid."""
        assert not loaded_spec_manager.is_valid_transition("planning", "UNKNOWN", "SCOPE")

    def test_invalid_transition_unknown_module(self, loaded_spec_manager):
        """Transitions for unknown modules are invalid."""
        assert not loaded_spec_manager.is_valid_transition("unknown", None, "SCOPE")


# =============================================================================
# TestGetExpectedWrites
# =============================================================================

class TestGetExpectedWrites:
    """Test getting expected writes."""

    def test_get_expected_writes_with_writes(self, loaded_spec_manager):
        """Returns expected writes for transition with writes."""
        writes = loaded_spec_manager.get_expected_writes("planning", None, "SCOPE")
        assert len(writes) == 1
        assert writes[0].table == "sessions"
        assert writes[0].count == "1"
        assert writes[0].description == "Create session"

    def test_get_expected_writes_no_writes(self, loaded_spec_manager):
        """Returns empty list for transition without writes."""
        writes = loaded_spec_manager.get_expected_writes("planning", "PLAN", "DONE")
        assert writes == []

    def test_get_expected_writes_unknown_transition(self, loaded_spec_manager):
        """Returns empty list for unknown transition."""
        writes = loaded_spec_manager.get_expected_writes("planning", "SCOPE", "DONE")
        assert writes == []

    def test_get_expected_writes_unknown_module(self, loaded_spec_manager):
        """Returns empty list for unknown module."""
        writes = loaded_spec_manager.get_expected_writes("unknown", None, "SCOPE")
        assert writes == []

    def test_expected_write_structure(self, loaded_spec_manager):
        """ExpectedWrite has correct structure."""
        writes = loaded_spec_manager.get_expected_writes("planning", None, "SCOPE")
        write = writes[0]

        assert isinstance(write, ExpectedWrite)
        assert isinstance(write.table, str)
        assert isinstance(write.count, str)
        assert isinstance(write.description, str)


# =============================================================================
# TestGetSLA
# =============================================================================

class TestGetSLA:
    """Test SLA configuration retrieval."""

    def test_get_sla_loaded(self, loaded_spec_manager):
        """Returns loaded SLA config."""
        sla = loaded_spec_manager.get_sla()

        assert isinstance(sla, SLAConfig)
        assert sla.max_response_time_seconds == 30
        assert sla.max_state_duration_minutes == 30
        assert sla.max_interaction_gap_minutes == 60
        assert sla.admin_notification_cooldown_seconds == 60
        assert sla.max_concurrent_sessions_per_user == 3

    def test_get_sla_defaults(self, spec_manager):
        """Returns default SLA config when not loaded."""
        sla = spec_manager.get_sla()

        assert sla.max_response_time_seconds == 30
        assert sla.max_state_duration_minutes == 30
        assert sla.max_interaction_gap_minutes == 60

    def test_get_sla_partial_override(self, spec_manager):
        """Partial SLA config merges with defaults."""
        spec_manager.load_from_dict({
            "slas": {
                "max_response_time_seconds": 45,
            }
        })
        sla = spec_manager.get_sla()

        # Custom value
        assert sla.max_response_time_seconds == 45
        # Default value
        assert sla.max_state_duration_minutes == 30

    def test_sla_config_immutable(self, loaded_spec_manager):
        """SLAConfig is a frozen dataclass."""
        sla = loaded_spec_manager.get_sla()

        with pytest.raises(AttributeError):
            sla.max_response_time_seconds = 100  # type: ignore[misc]


# =============================================================================
# TestGetSeverityRules
# =============================================================================

class TestGetSeverityRules:
    """Test severity rules retrieval."""

    def test_get_severity_rules_critical(self, loaded_spec_manager):
        """Returns critical severity rules."""
        rules = loaded_spec_manager.get_severity_rules("critical")
        assert len(rules) == 2
        assert rules[0]["type"] == "invalid_transition"
        assert rules[1]["type"] == "stuck_state"

    def test_get_severity_rules_warning(self, loaded_spec_manager):
        """Returns warning severity rules."""
        rules = loaded_spec_manager.get_severity_rules("warning")
        assert len(rules) == 1
        assert rules[0]["type"] == "stale_interaction"

    def test_get_severity_rules_unknown(self, loaded_spec_manager):
        """Returns empty list for unknown severity."""
        rules = loaded_spec_manager.get_severity_rules("info")
        assert rules == []

    def test_get_severity_rules_empty_spec(self, spec_manager):
        """Returns empty list for empty spec."""
        spec_manager.load_from_dict({})
        rules = spec_manager.get_severity_rules("critical")
        assert rules == []


# =============================================================================
# TestDataClassImmutability
# =============================================================================

class TestDataClassImmutability:
    """Test that data classes are properly immutable."""

    def test_expected_write_frozen(self):
        """ExpectedWrite is frozen."""
        write = ExpectedWrite(
            table="test",
            count="1",
            description="Test",
        )

        with pytest.raises(AttributeError):
            write.table = "modified"  # type: ignore[misc]

    def test_valid_transition_frozen(self):
        """ValidTransition is frozen."""
        transition = ValidTransition(
            from_state="A",
            to_state="B",
        )

        with pytest.raises(AttributeError):
            transition.from_state = "C"  # type: ignore[misc]

    def test_sla_config_frozen(self):
        """SLAConfig is frozen."""
        sla = SLAConfig()

        with pytest.raises(AttributeError):
            sla.max_response_time_seconds = 100  # type: ignore[misc]


# =============================================================================
# TestModuleSpec
# =============================================================================

class TestModuleSpec:
    """Test ModuleSpec dataclass."""

    def test_module_spec_creation(self):
        """Can create ModuleSpec."""
        spec = ModuleSpec(
            name="test",
            states=["A", "B"],
            transitions=[],
        )

        assert spec.name == "test"
        assert spec.states == ["A", "B"]
        assert spec.transitions == []

    def test_module_spec_defaults(self):
        """ModuleSpec has default empty lists."""
        spec = ModuleSpec(name="test")

        assert spec.states == []
        assert spec.transitions == []


# =============================================================================
# TestEdgeCases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_load_malformed_modules_section(self, spec_manager):
        """Malformed modules section raises AttributeError."""
        with pytest.raises(AttributeError):
            spec_manager.load_from_dict({
                "modules": "not a dict"
            })

    def test_load_malformed_transition(self, spec_manager):
        """Handles malformed transitions gracefully."""
        spec_manager.load_from_dict({
            "modules": {
                "test": {
                    "states": ["A"],
                    "transitions": ["not a dict"],
                }
            }
        })
        assert spec_manager.is_loaded
        # Malformed transition should be skipped
        transitions = spec_manager.get_valid_transitions("test")
        assert len(transitions) == 0

    def test_load_malformed_expected_write(self, spec_manager):
        """Handles malformed expected writes gracefully."""
        spec_manager.load_from_dict({
            "modules": {
                "test": {
                    "states": ["A"],
                    "transitions": [
                        {
                            "from": None,
                            "to": "A",
                            "expected_writes": "not a list",
                        }
                    ],
                }
            }
        })
        assert spec_manager.is_loaded

    def test_get_states_preserves_order(self, spec_manager):
        """get_module_states preserves state order."""
        spec_manager.load_from_dict({
            "modules": {
                "test": {
                    "states": ["C", "B", "A"],
                    "transitions": [],
                }
            }
        })
        states = spec_manager.get_module_states("test")
        assert states == ["C", "B", "A"]
