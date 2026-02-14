"""
Module Registry for Aurora Sun V1.

Discovers and routes to modules. Adding a module = register + done.
The registry maintains the mapping from intents to modules.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

import logging

from .daily_workflow_hooks import DailyWorkflowHook
from .module_protocol import Module

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Discovers and routes to modules.

    This is the central registry for all modules. It maintains:
    - _modules: Map of module name -> Module instance
    - _intent_map: Map of intent string -> Module instance

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
        self._intent_map: dict[str, Module] = {}
        self._initialized: bool = False

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
                existing = self._intent_map[intent]
                raise ValueError(
                    f"Intent '{intent}' is already registered to module '{existing.name}'. "
                    f"Cannot register to '{module.name}'."
                )

        # Register the module
        self._modules[module.name] = module

        # Register all intents
        for intent in module.intents:
            self._intent_map[intent] = module

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
            intent for intent, mod in self._intent_map.items()
            if mod.name == module_name
        ]
        for intent in intents_to_remove:
            del self._intent_map[intent]

        logger.info(f"Deregistered module '{module_name}'")
        return True

    def route(self, intent: str) -> Module | None:
        """Route an intent to the appropriate module.

        Args:
            intent: The intent to route (e.g., "planning.start", "habit.list")

        Returns:
            The Module that handles this intent, or None if not found
        """
        return self._intent_map.get(intent)

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
        return {
            intent: module.name
            for intent, module in self._intent_map.items()
        }

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
