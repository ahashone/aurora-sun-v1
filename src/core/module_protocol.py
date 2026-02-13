"""
Module Protocol for Aurora Sun V1.

Every module implements this interface. This is the contract between
the Module System and individual modules (Planning, Habits, Beliefs, etc.).

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from typing import Literal, Protocol, Optional
from typing_extensions import TypeAlias

from .module_context import ModuleContext
from .module_response import ModuleResponse
from .daily_workflow_hooks import DailyWorkflowHooks


# Pillar types as defined in ARCHITECTURE.md
Pillar: TypeAlias = Literal["vision_to_task", "second_brain", "money"]


class Module(Protocol):
    """Every module implements this interface. No exceptions."""

    # Module identity
    name: str  # "planning", "habits", "beliefs", ...
    intents: list[str]  # Intents this module handles (e.g., ["planning.start", "planning.priorities"])
    pillar: Pillar  # "vision_to_task" | "second_brain" | "money"

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,
    ) -> ModuleResponse:
        """Handle a user message within this module.

        Args:
            message: The user's input message
            ctx: Module context containing user_id, segment_context, state, session_id, language

        Returns:
            ModuleResponse with text, optional buttons, next_state, and optional side_effects
        """
        ...

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """Called when user enters this module.

        Args:
            ctx: Module context

        Returns:
            ModuleResponse with welcome message, initial prompt, or state transition
        """
        ...

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Called when user leaves this module (cleanup).

        Args:
            ctx: Module context
        """
        ...

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """Return hooks for the daily workflow (morning, midday, evening).

        Returns:
            DailyWorkflowHooks with optional callables for each workflow phase
        """
        ...

    async def export_user_data(self, user_id: int) -> dict:
        """GDPR export for this module's data.

        Args:
            user_id: The user's ID

        Returns:
            Dict containing all user data from this module, keyed by data type
        """
        ...

    async def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for this module's data.

        Args:
            user_id: The user's ID
        """
        ...

    async def freeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Restriction of processing.

        Called when user requests restriction of processing.
        Data is retained but not processed.

        Args:
            user_id: The user's ID
        """
        ...

    async def unfreeze_user_data(self, user_id: int) -> None:
        """GDPR Art. 18: Lift restriction of processing.

        Called when user consents to processing again or withdraws deletion request.

        Args:
            user_id: The user's ID
        """
        ...


# Type alias for module instances
ModuleInstance: TypeAlias = Module
