"""
i18n Foundation for Aurora Sun V1.

This module provides the internationalization (i18n) foundation for Aurora Sun.
Supported languages: English (en), German (de), Serbian (sr), Greek (el).

All user-facing strings should be accessed through the translation system,
never hardcoded.

Reference: CLAUDE.md - International Audience
"""

from __future__ import annotations

from typing import Literal

# Supported languages (ISO 639-1 codes)
LANGUAGES: list[str] = ["en", "de", "sr", "el"]

# Language codes (used as type alias)
LanguageCode = Literal["en", "de", "sr", "el"]

# Default language
DEFAULT_LANGUAGE: LanguageCode = "en"

# Language display names (for UI)
LANGUAGE_DISPLAY_NAMES: dict[LanguageCode, str] = {
    "en": "English",
    "de": "Deutsch",
    "sr": "Srpski",
    "el": "Ελληνικά",
}


def is_valid_language(lang: str) -> bool:
    """
    Check if a language code is valid.

    Args:
        lang: Language code to validate

    Returns:
        True if valid, False otherwise
    """
    return lang in LANGUAGES


def get_language_display_name(lang: LanguageCode) -> str:
    """
    Get the display name for a language code.

    Args:
        lang: Language code

    Returns:
        Human-readable language name (e.g., "English", "Deutsch")
    """
    return LANGUAGE_DISPLAY_NAMES.get(lang, lang)
