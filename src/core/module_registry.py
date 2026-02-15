"""
Module Registry for Aurora Sun V1.

Discovers and routes to modules. Adding a module = register + done.
The registry maintains the mapping from intents to modules.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

import logging
import weakref
from typing import Any

from .daily_workflow_hooks import DailyWorkflowHook
from .module_protocol import Module

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Discovers and routes to modules.

    This is the central registry for all modules. It maintains:
    - _modules: Map of module name -> Module instance (single strong reference)
    - _intent_map: Map of intent string -> module name (string, not a reference)

    PERF-006: The intent map stores module names (strings) rather than direct
    Module references, eliminating duplicate strong references that could
    prevent garbage collection after deregister(). A weakref finalizer is
    registered per module to auto-clean stale intent mappings if a module
    is garbage collected while still registered (defensive measure).

    Adding a new module means implementing Module(Protocol) and registering.
    The router then automatically handles those intents.

    Example:
        registry = ModuleRegistry()
        registry.register(PlanningModule())
        registry.register(HabitsModule())

        # Route an intent
        module = registry.route("planning.start")
        if module:
            response = await module.handle(message, ctx)
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._modules: dict[str, Module] = {}
        self._intent_map: dict[str, str] = {}  # PERF-006: intent -> module name (not reference)
        self._finalizers: dict[str, Any] = {}  # PERF-006: weakref.finalize cleanup callbacks
        self._initialized: bool = False

    def _make_finalizer(self, module_name: str) -> Any:
        """Create a weak reference finalizer for a module.

        When a module is garbage collected, this callback removes
        any stale intent mappings from _intent_map.

        Args:
            module_name: The module name to clean up

        Returns:
            A weakref.finalize object
        """
        def _cleanup(name: str) -> None:
            # Remove stale intents pointing to this module
            stale = [i for i, m in self._intent_map.items() if m == name]
            for intent in stale:
                del self._intent_map[intent]
            self._finalizers.pop(name, None)
            logger.debug("Cleaned up stale references for module '%s'", name)

        module = self._modules.get(module_name)
        if module is None:
            raise ValueError(f"Module '{module_name}' not found for finalizer")
        return weakref.finalize(module, _cleanup, module_name)

    def register(self, module: Module) -> None:
        """Register a module with the registry.

        Adds the module to the internal maps. Also registers all
        the module's intents for routing.

        Args:
            module: A Module instance to register

        Raises:
            ValueError: If module name or intents conflict with existing modules
        """
        # Check for name conflicts
        if module.name in self._modules:
            raise ValueError(
                f"Module '{module.name}' is already registered. "
                f"Use a different name or deregister the existing module first."
            )

        # Check for intent conflicts
        for intent in module.intents:
            if intent in self._intent_map:
                existing_name = self._intent_map[intent]
                raise ValueError(
                    f"Intent '{intent}' is already registered to module '{existing_name}'. "
                    f"Cannot register to '{module.name}'."
                )

        # Register the module (single strong reference)
        self._modules[module.name] = module

        # Register all intents (store module name, not reference)
        for intent in module.intents:
            self._intent_map[intent] = module.name

        # PERF-006: Register weakref finalizer for defensive cleanup
        self._finalizers[module.name] = self._make_finalizer(module.name)

        logger.info(
            f"Registered module '{module.name}' with intents: {module.intents}"
        )

    def deregister(self, module_name: str) -> bool:
        """Deregister a module from the registry.

        Removes the module and all its intent mappings.

        Args:
            module_name: The name of the module to deregister

        Returns:
            True if the module was found and removed, False otherwise
        """
        module = self._modules.pop(module_name, None)
        if module is None:
            return False

        # Remove all intent mappings for this module
        intents_to_remove = [
            intent for intent, mod_name in self._intent_map.items()
            if mod_name == module_name
        ]
        for intent in intents_to_remove:
            del self._intent_map[intent]

        # PERF-006: Detach the finalizer to avoid double cleanup
        finalizer = self._finalizers.pop(module_name, None)
        if finalizer is not None:
            finalizer.detach()

        logger.info(f"Deregistered module '{module_name}'")
        return True

    def route(self, intent: str) -> Module | None:
        """Route an intent to the appropriate module.

        Args:
            intent: The intent to route (e.g., "planning.start", "habit.list")

        Returns:
            The Module that handles this intent, or None if not found
        """
        module_name = self._intent_map.get(intent)
        if module_name is None:
            return None
        return self._modules.get(module_name)

    def get_module(self, name: str) -> Module | None:
        """Get a module by name.

        Args:
            name: The module name

        Returns:
            The Module instance, or None if not found
        """
        return self._modules.get(name)

    def list_modules(self) -> list[str]:
        """List all registered module names.

        Returns:
            List of module names
        """
        return list(self._modules.keys())

    def list_intents(self) -> dict[str, str]:
        """List all registered intents and their modules.

        Returns:
            Dict mapping intent -> module name
        """
        return dict(self._intent_map)

    def get_daily_hooks(self) -> dict[str, list[DailyWorkflowHook]]:
        """Collect all daily workflow hooks from all modules.

        Returns:
            Dict mapping hook stage (morning, planning_enrichment, etc.)
            to list of hook callables from all modules
        """
        hooks: dict[str, list[DailyWorkflowHook]] = {
            "morning": [],
            "planning_enrichment": [],
            "midday_check": [],
            "evening_review": [],
        }

        for module in self._modules.values():
            module_hooks = module.get_daily_workflow_hooks()

            if module_hooks.morning is not None:
                hooks["morning"].append(module_hooks.morning)
            if module_hooks.planning_enrichment is not None:
                hooks["planning_enrichment"].append(module_hooks.planning_enrichment)
            if module_hooks.midday_check is not None:
                hooks["midday_check"].append(module_hooks.midday_check)
            if module_hooks.evening_review is not None:
                hooks["evening_review"].append(module_hooks.evening_review)

        logger.debug(
            f"Collected daily workflow hooks: "
            f"morning={len(hooks['morning'])}, "
            f"planning_enrichment={len(hooks['planning_enrichment'])}, "
            f"midday_check={len(hooks['midday_check'])}, "
            f"evening_review={len(hooks['evening_review'])}"
        )

        return hooks

    def is_registered(self, module_name: str) -> bool:
        """Check if a module is registered.

        Args:
            module_name: The module name to check

        Returns:
            True if the module is registered
        """
        return module_name in self._modules

    def clear(self) -> None:
        """Clear all registered modules and intents.

        Useful for testing or hot-reloading.
        """
        # PERF-006: Detach all finalizers before clearing
        for finalizer in self._finalizers.values():
            finalizer.detach()
        self._finalizers.clear()
        self._modules.clear()
        self._intent_map.clear()
        logger.info("Cleared all modules from registry")

    @property
    def module_count(self) -> int:
        """Get the number of registered modules."""
        return len(self._modules)

    @property
    def intent_count(self) -> int:
        """Get the number of registered intents."""
        return len(self._intent_map)


# Global registry instance
# Modules should be registered at application startup
_global_registry: ModuleRegistry | None = None


def get_registry() -> ModuleRegistry:
    """Get the global module registry instance.

    Returns:
        The global ModuleRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ModuleRegistry()
    return _global_registry


def set_registry(registry: ModuleRegistry) -> None:
    """Set the global module registry instance.

    Args:
        registry: The ModuleRegistry to use globally
    """
    global _global_registry
    _global_registry = registry
