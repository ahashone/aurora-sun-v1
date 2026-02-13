"""
Daily Workflow Hooks for Aurora Sun V1.

Defines how modules participate in the daily workflow engine.
Hooks are called at specific times during the daily cycle.

Reference: ARCHITECTURE.md Section 3 (Daily Workflow Engine)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .module_context import ModuleContext
    from .module_response import ModuleResponse


# Type for hook callables
# Each hook receives ModuleContext and returns optional ModuleResponse or data
DailyWorkflowHook: TypeAlias = Callable[["ModuleContext"], Optional[Any]]


@dataclass
class DailyWorkflowHooks:
    """How a module participates in the daily workflow.

    Each field is an optional callable that will be invoked at
    the corresponding stage of the daily workflow.

    Examples:
        - Habits module: morning = "habit reminders", evening = "habit check-in"
        - Beliefs module: planning_enrichment = "surface blocking beliefs"
        - Motifs module: planning_enrichment = "suggest motif-aligned tasks"
        - Capture module: planning_enrichment = "surface captured tasks/ideas"
        - Money module: evening = "daily spending summary" (if enabled)

    Attributes:
        morning: Called during morning activation
        planning_enrichment: Called before/during planning
        midday_check: Called during midday reminder
        evening_review: Called during auto-review
    """

    # Workflow stage hooks
    morning: Optional[DailyWorkflowHook] = None
    planning_enrichment: Optional[DailyWorkflowHook] = None
    midday_check: Optional[DailyWorkflowHook] = None
    evening_review: Optional[DailyWorkflowHook] = None

    # Metadata
    hook_name: str = ""  # Name of the module providing these hooks
    priority: int = 0  # Execution priority (lower = earlier)

    def has_any_hook(self) -> bool:
        """Check if any hook is defined.

        Returns:
            True if at least one hook is defined
        """
        return any([
            self.morning is not None,
            self.planning_enrichment is not None,
            self.midday_check is not None,
            self.evening_review is not None,
        ])

    def get_active_hooks(self) -> dict[str, DailyWorkflowHook]:
        """Get a dict of only the hooks that are defined.

        Returns:
            Dict mapping hook name to hook callable
        """
        hooks = {}
        if self.morning is not None:
            hooks["morning"] = self.morning
        if self.planning_enrichment is not None:
            hooks["planning_enrichment"] = self.planning_enrichment
        if self.midday_check is not None:
            hooks["midday_check"] = self.midday_check
        if self.evening_review is not None:
            hooks["evening_review"] = self.evening_review
        return hooks


# Type alias for the module hook provider
ModuleHookProvider: TypeAlias = DailyWorkflowHooks


# Example hook implementations (for reference):

# def habits_morning_hook(ctx: ModuleContext) -> Optional[str]:
#     """Example: Return morning habit reminder message."""
#     return "Don't forget your morning meditation!"


# def beliefs_planning_enrichment_hook(ctx: ModuleContext) -> Optional[list[str]]:
#     """Example: Return beliefs that might block current goals."""
#     return ["You don't believe you deserve success yet."]


# def money_evening_review_hook(ctx: ModuleContext) -> Optional[str]:
#     """Example: Return daily spending summary."""
#     return "Today you spent $45. Remaining budget: $200."
