"""
Module Response for Aurora Sun V1.

The response object returned by every module operation.
Contains text, UI elements, state transitions, and side effects.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .buttons import Button
from .side_effects import SideEffect


@dataclass
class ModuleResponse:
    """Response returned by module handle/on_enter operations.

    This is the primary response object that modules return.
    It contains everything needed to respond to the user and
    update the system state.

    Attributes:
        text: The response text to show to the user
        buttons: Optional list of buttons to display
        next_state: Optional state to transition to (if None, state unchanged)
        side_effects: Optional list of side effects to execute
        metadata: Additional response metadata
    """

    # Primary response content
    text: str

    # UI elements
    buttons: list[Button] | None = None

    # State transition
    next_state: str | None = None

    # System actions
    side_effects: list[SideEffect] | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Response modifiers
    is_end_of_flow: bool = False  # True if this response ends the module flow
    should_trigger_daily_workflow: bool = False  # Trigger daily workflow after response

    def add_button(self, text: str, callback_data: str | None = None, url: str | None = None) -> None:
        """Add a button to the response.

        Args:
            text: Button text
            callback_data: Callback data for inline buttons
            url: URL for URL buttons
        """
        if self.buttons is None:
            self.buttons = []
        self.buttons.append(Button(text=text, callback_data=callback_data, url=url))

    def add_side_effect(self, effect_type: str, payload: dict[str, Any]) -> None:
        """Add a side effect to the response.

        Args:
            effect_type: Type of effect (e.g., "save_task", "update_goal")
            payload: Effect payload
        """
        if self.side_effects is None:
            self.side_effects = []
        self.side_effects.append(SideEffect(effect_type=effect_type, payload=payload))

    @classmethod
    def text_only(cls, text: str) -> ModuleResponse:
        """Create a simple text-only response.

        Args:
            text: The response text

        Returns:
            ModuleResponse with just text
        """
        return cls(text=text)

    @classmethod
    def with_buttons(cls, text: str, buttons: list[Button]) -> ModuleResponse:
        """Create a response with buttons.

        Args:
            text: The response text
            buttons: List of buttons

        Returns:
            ModuleResponse with text and buttons
        """
        return cls(text=text, buttons=buttons)

    @classmethod
    def end_flow(cls, text: str) -> ModuleResponse:
        """Create a response that ends the module flow.

        Args:
            text: The final message

        Returns:
            ModuleResponse that ends the flow
        """
        return cls(text=text, is_end_of_flow=True)

    @classmethod
    def transition(cls, text: str, next_state: str) -> ModuleResponse:
        """Create a response with a state transition.

        Args:
            text: The response text
            next_state: The next state to transition to

        Returns:
            ModuleResponse with state transition
        """
        return cls(text=text, next_state=next_state)

