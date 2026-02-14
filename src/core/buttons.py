"""
Button types for Aurora Sun V1.

Defines button types used in ModuleResponse for user interactions.

Reference: ARCHITECTURE.md Section 2 (Module System)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ButtonType(Enum):
    """Types of buttons supported."""

    # Inline button with callback data (handled in bot)
    INLINE = "inline"

    # URL button that opens external link
    URL = "url"

    # Switch to inline query
    SWITCH_INLINE = "switch_inline"

    # Switch to inline query in current chat
    SWITCH_INLINE_CURRENT = "switch_inline_current"


@dataclass
class Button:
    """A button displayed to the user.

    Buttons can be either inline (with callback_data) or URL buttons.
    Inline buttons trigger a callback query that the bot handles.

    Attributes:
        text: The button text displayed to the user
        callback_data: Data sent back when button is clicked (for inline buttons)
        url: URL to open when button is clicked (for URL buttons)
        button_type: Type of button (inline, url, etc.)
    """

    text: str
    callback_data: str | None = None
    url: str | None = None
    button_type: ButtonType = ButtonType.INLINE

    def __post_init__(self) -> None:
        """Validate button configuration."""
        if self.callback_data and self.url:
            raise ValueError("Button cannot have both callback_data and url")

        if self.callback_data:
            self.button_type = ButtonType.INLINE
        elif self.url:
            self.button_type = ButtonType.URL

    @classmethod
    def inline(cls, text: str, callback_data: str) -> Button:
        """Create an inline button.

        Args:
            text: Button text
            callback_data: Callback data

        Returns:
            Button instance
        """
        return cls(text=text, callback_data=callback_data)

    @classmethod
    def url_button(cls, text: str, target_url: str) -> Button:
        """Create a URL button.

        Args:
            text: Button text
            target_url: Target URL

        Returns:
            Button instance
        """
        return cls(text=text, url=target_url)

    @classmethod
    def switch_inline(cls, text: str, query: str) -> Button:
        """Create a switch to inline query button.

        Args:
            text: Button text
            query: Inline query to switch to

        Returns:
            Button instance
        """
        return cls(text=text, callback_data=f"switch_inline:{query}", button_type=ButtonType.SWITCH_INLINE)

    def to_telegram_format(self) -> dict[str, Any]:
        """Convert to Telegram button format.

        Returns:
            Dict suitable for telegram.SendMessage reply_markup
        """
        if self.button_type == ButtonType.URL:
            return {
                "text": self.text,
                "url": self.url,
            }
        else:
            return {
                "text": self.text,
                "callback_data": self.callback_data,
            }


@dataclass
class ButtonRow:
    """A row of buttons displayed together."""

    buttons: list[Button] = field(default_factory=list)

    def add_button(self, button: Button) -> None:
        """Add a button to this row."""
        self.buttons.append(button)

    def to_telegram_format(self) -> list[dict[str, Any]]:
        """Convert to Telegram format."""
        return [button.to_telegram_format() for button in self.buttons]


@dataclass
class ButtonGrid:
    """A grid of buttons (multiple rows)."""

    rows: list[ButtonRow] = field(default_factory=list)

    def add_row(self, row: ButtonRow) -> None:
        """Add a row to the grid."""
        self.rows.append(row)

    def add_inline_buttons(self, *buttons: Button) -> None:
        """Add a row of inline buttons."""
        row = ButtonRow(buttons=list(buttons))
        self.rows.append(row)

    def to_telegram_format(self) -> list[list[dict[str, Any]]]:
        """Convert to Telegram inline keyboard format."""
        return [row.to_telegram_format() for row in self.rows]


# Type alias for backward compatibility
InlineKeyboardButton = Button
InlineKeyboardMarkup = ButtonGrid
