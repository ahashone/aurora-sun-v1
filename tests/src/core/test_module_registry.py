"""
Tests for ModuleRegistry.

Covers:
- Module registration and deregistration
- Intent routing
- Module lookup
- Daily workflow hooks collection
- Error handling (name conflicts, intent conflicts)
"""

import pytest

from src.core.daily_workflow_hooks import DailyWorkflowHooks
from src.core.module_registry import ModuleRegistry

# =============================================================================
# Mock Module for Testing
# =============================================================================


class MockModule:
    """Mock module for testing."""

    def __init__(self, name: str, intents: list[str]):
        self._name = name
        self._intents = intents

    @property
    def name(self) -> str:
        return self._name

    @property
    def intents(self) -> list[str]:
        return self._intents

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        return DailyWorkflowHooks()


class MockModuleWithHooks(MockModule):
    """Mock module with daily workflow hooks."""

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        async def morning_hook(user_id, context):
            return "Morning!"

        async def evening_hook(user_id, context):
            return "Evening!"

        return DailyWorkflowHooks(
            morning=morning_hook,
            evening_review=evening_hook,
        )


# =============================================================================
# ModuleRegistry Tests
# =============================================================================


def test_registry_initialization():
    """Test creating a new registry."""
    registry = ModuleRegistry()
    assert registry.module_count == 0
    assert registry.intent_count == 0
    assert registry.list_modules() == []


def test_register_module():
    """Test registering a module."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start", "planning.view"])

    registry.register(module)

    assert registry.module_count == 1
    assert registry.intent_count == 2
    assert "planning" in registry.list_modules()


def test_register_multiple_modules():
    """Test registering multiple modules."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start", "planning.view"])
    habits = MockModule("habits", ["habits.list", "habits.complete"])
    beliefs = MockModule("beliefs", ["beliefs.list"])

    registry.register(planning)
    registry.register(habits)
    registry.register(beliefs)

    assert registry.module_count == 3
    assert registry.intent_count == 5
    assert set(registry.list_modules()) == {"planning", "habits", "beliefs"}


def test_register_duplicate_name_fails():
    """Test that registering a module with duplicate name fails."""
    registry = ModuleRegistry()
    module1 = MockModule("planning", ["planning.start"])
    module2 = MockModule("planning", ["planning.different"])

    registry.register(module1)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(module2)


def test_register_duplicate_intent_fails():
    """Test that registering a module with duplicate intent fails."""
    registry = ModuleRegistry()
    module1 = MockModule("planning", ["planning.start"])
    module2 = MockModule("other", ["planning.start"])

    registry.register(module1)

    with pytest.raises(ValueError, match="already registered to module"):
        registry.register(module2)


def test_deregister_module():
    """Test deregistering a module."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start", "planning.view"])

    registry.register(module)
    assert registry.module_count == 1

    result = registry.deregister("planning")

    assert result is True
    assert registry.module_count == 0
    assert registry.intent_count == 0


def test_deregister_nonexistent_module():
    """Test deregistering a module that doesn't exist."""
    registry = ModuleRegistry()
    result = registry.deregister("nonexistent")
    assert result is False


def test_deregister_removes_intents():
    """Test that deregistering removes all intents."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start", "planning.view"])

    registry.register(module)
    registry.deregister("planning")

    assert registry.route("planning.start") is None
    assert registry.route("planning.view") is None


def test_route_intent():
    """Test routing an intent to the correct module."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start"])
    habits = MockModule("habits", ["habits.list"])

    registry.register(planning)
    registry.register(habits)

    assert registry.route("planning.start") == planning
    assert registry.route("habits.list") == habits


def test_route_unknown_intent():
    """Test routing an unknown intent."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start"])
    registry.register(planning)

    assert registry.route("unknown.intent") is None


def test_get_module():
    """Test getting a module by name."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start"])
    registry.register(module)

    retrieved = registry.get_module("planning")
    assert retrieved == module


def test_get_nonexistent_module():
    """Test getting a module that doesn't exist."""
    registry = ModuleRegistry()
    assert registry.get_module("nonexistent") is None


def test_list_modules():
    """Test listing all modules."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start"])
    habits = MockModule("habits", ["habits.list"])

    registry.register(planning)
    registry.register(habits)

    modules = registry.list_modules()
    assert set(modules) == {"planning", "habits"}


def test_list_intents():
    """Test listing all intents."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start", "planning.view"])
    habits = MockModule("habits", ["habits.list"])

    registry.register(planning)
    registry.register(habits)

    intents = registry.list_intents()
    assert intents == {
        "planning.start": "planning",
        "planning.view": "planning",
        "habits.list": "habits",
    }


def test_is_registered():
    """Test checking if a module is registered."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start"])

    assert registry.is_registered("planning") is False

    registry.register(module)
    assert registry.is_registered("planning") is True

    registry.deregister("planning")
    assert registry.is_registered("planning") is False


def test_clear():
    """Test clearing all modules."""
    registry = ModuleRegistry()
    planning = MockModule("planning", ["planning.start"])
    habits = MockModule("habits", ["habits.list"])

    registry.register(planning)
    registry.register(habits)

    assert registry.module_count == 2

    registry.clear()

    assert registry.module_count == 0
    assert registry.intent_count == 0
    assert registry.list_modules() == []


def test_get_daily_hooks_no_modules():
    """Test getting daily hooks when no modules are registered."""
    registry = ModuleRegistry()
    hooks = registry.get_daily_hooks()

    assert hooks["morning"] == []
    assert hooks["planning_enrichment"] == []
    assert hooks["midday_check"] == []
    assert hooks["evening_review"] == []


def test_get_daily_hooks_with_modules():
    """Test getting daily hooks from modules."""
    registry = ModuleRegistry()

    # Module with hooks
    module_with_hooks = MockModuleWithHooks("planning", ["planning.start"])
    registry.register(module_with_hooks)

    # Module without hooks
    module_no_hooks = MockModule("habits", ["habits.list"])
    registry.register(module_no_hooks)

    hooks = registry.get_daily_hooks()

    assert len(hooks["morning"]) == 1
    assert len(hooks["evening_review"]) == 1
    assert len(hooks["planning_enrichment"]) == 0
    assert len(hooks["midday_check"]) == 0


def test_module_count_property():
    """Test module_count property."""
    registry = ModuleRegistry()
    assert registry.module_count == 0

    registry.register(MockModule("m1", ["i1"]))
    assert registry.module_count == 1

    registry.register(MockModule("m2", ["i2"]))
    assert registry.module_count == 2

    registry.deregister("m1")
    assert registry.module_count == 1


def test_intent_count_property():
    """Test intent_count property."""
    registry = ModuleRegistry()
    assert registry.intent_count == 0

    registry.register(MockModule("m1", ["i1", "i2"]))
    assert registry.intent_count == 2

    registry.register(MockModule("m2", ["i3"]))
    assert registry.intent_count == 3

    registry.deregister("m1")
    assert registry.intent_count == 1


# =============================================================================
# Global Registry Tests
# =============================================================================


def test_get_registry():
    """Test getting the global registry."""
    from src.core.module_registry import get_registry

    registry1 = get_registry()
    registry2 = get_registry()

    # Should return the same instance
    assert registry1 is registry2


def test_set_registry():
    """Test setting a custom global registry."""
    from src.core.module_registry import get_registry, set_registry

    custom_registry = ModuleRegistry()
    custom_registry.register(MockModule("custom", ["custom.intent"]))

    set_registry(custom_registry)

    retrieved = get_registry()
    assert retrieved is custom_registry
    assert retrieved.is_registered("custom")


# =============================================================================
# Edge Cases
# =============================================================================


def test_register_module_with_no_intents():
    """Test registering a module with no intents."""
    registry = ModuleRegistry()
    module = MockModule("empty", [])

    registry.register(module)

    assert registry.module_count == 1
    assert registry.intent_count == 0


def test_deregister_after_registering_multiple():
    """Test that deregistering one module doesn't affect others."""
    registry = ModuleRegistry()
    m1 = MockModule("m1", ["i1"])
    m2 = MockModule("m2", ["i2"])
    m3 = MockModule("m3", ["i3"])

    registry.register(m1)
    registry.register(m2)
    registry.register(m3)

    registry.deregister("m2")

    assert registry.module_count == 2
    assert registry.intent_count == 2
    assert registry.route("i1") == m1
    assert registry.route("i2") is None
    assert registry.route("i3") == m3


def test_clear_and_re_register():
    """Test clearing and re-registering modules."""
    registry = ModuleRegistry()
    module = MockModule("planning", ["planning.start"])

    registry.register(module)
    registry.clear()

    # Should be able to register again after clear
    registry.register(module)
    assert registry.module_count == 1
    assert registry.route("planning.start") == module
