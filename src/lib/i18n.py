"""
Full i18n System for Aurora Sun V1.

Extends the existing i18n/__init__.py and i18n/strings.py foundation.

Features:
- Auto-language detection from Telegram locale
- Support for 4 languages: en, de, sr, el (extensible)
- Segment name translation per language
- Module string registry
- Fallback to English if translation missing
- Format string interpolation with safety checks

This module provides the extended i18n service layer that sits on top of
the string translation system in src/i18n/strings.py.

Reference: CLAUDE.md - International Audience, ROADMAP 5.1
"""

from __future__ import annotations

import logging
from typing import Any

from src.i18n import DEFAULT_LANGUAGE, LANGUAGES, LanguageCode, is_valid_language
from src.i18n.strings import get_supported_languages, t, t_segment

logger = logging.getLogger(__name__)


class I18nService:
    """
    Internationalization service for Aurora Sun V1.

    Handles:
    - Language detection from Telegram locale
    - Translation string retrieval with fallback
    - Segment name translation
    - Module string registration (for extensibility)
    """

    def __init__(self) -> None:
        """Initialize the i18n service."""
        self._custom_strings: dict[str, dict[str, dict[str, str]]] = {}

    def detect_language_from_locale(self, telegram_locale: str | None) -> LanguageCode:
        """
        Detect language from Telegram user's locale.

        Telegram locale format: "en-US", "de-DE", "sr-RS", "el-GR", etc.
        We extract the first 2 characters and check if we support it.

        Args:
            telegram_locale: Telegram user's locale (e.g., "en-US")

        Returns:
            Supported language code, or English if not supported
        """
        if not telegram_locale:
            return DEFAULT_LANGUAGE

        # Extract language code (first 2 characters)
        lang_code = telegram_locale.split("-")[0].lower()

        # Check if we support this language
        if is_valid_language(lang_code):
            return lang_code  # type: ignore[return-value]

        # Fallback to English
        logger.info(
            f"Unsupported locale '{telegram_locale}', falling back to English"
        )
        return DEFAULT_LANGUAGE

    def translate(
        self,
        lang: LanguageCode,
        module: str,
        key: str,
        **kwargs: Any,
    ) -> str:
        """
        Get a translated string.

        This is a wrapper around src.i18n.strings.t() with additional
        support for custom module strings.

        Args:
            lang: Language code (en, de, sr, el)
            module: Module name (e.g., "onboarding", "common")
            key: Translation key
            **kwargs: Optional format variables

        Returns:
            Translated string, or English fallback if not found
        """
        # Check custom strings first
        if lang in self._custom_strings:
            if module in self._custom_strings[lang]:
                if key in self._custom_strings[lang][module]:
                    template = self._custom_strings[lang][module][key]
                    return self._format_string(template, **kwargs)

        # Fall back to built-in translations
        return t(lang, module, key, **kwargs)

    def translate_segment(self, lang: LanguageCode, segment_code: str) -> str:
        """
        Get the translated segment display name.

        Args:
            lang: Language code
            segment_code: Internal segment code (AD, AU, AH, NT, CU)

        Returns:
            Translated segment display name
        """
        return t_segment(lang, segment_code)

    def register_module_strings(
        self,
        module_name: str,
        strings: dict[LanguageCode, dict[str, str]],
    ) -> None:
        """
        Register custom strings for a module.

        This allows modules to register their own translation strings
        at runtime (e.g., for plugins, custom interventions).

        Args:
            module_name: Module name
            strings: Dict mapping language codes to key-value pairs

        Example:
            >>> service.register_module_strings("my_module", {
            ...     "en": {"greeting": "Hello"},
            ...     "de": {"greeting": "Hallo"},
            ... })
        """
        for lang_code, lang_strings in strings.items():
            if lang_code not in self._custom_strings:
                self._custom_strings[lang_code] = {}
            if module_name not in self._custom_strings[lang_code]:
                self._custom_strings[lang_code][module_name] = {}

            self._custom_strings[lang_code][module_name].update(lang_strings)

        logger.info(f"Registered strings for module '{module_name}'")

    def get_supported_languages(self) -> list[str]:
        """
        Get list of all supported language codes.

        Returns:
            List of supported language codes
        """
        return get_supported_languages()

    def validate_language(self, lang: str) -> bool:
        """
        Check if a language code is valid.

        Args:
            lang: Language code to validate

        Returns:
            True if valid, False otherwise
        """
        return is_valid_language(lang)

    @staticmethod
    def _format_string(template: str, **kwargs: Any) -> str:
        """
        Safely format a template string with variables.

        Args:
            template: Template string with {key} placeholders
            **kwargs: Format variables

        Returns:
            Formatted string
        """
        if not kwargs:
            return template

        # Type guard: only allow safe types to prevent
        # format string injection via __format__ abuse
        safe_kwargs: dict[str, str | int | float] = {}
        for k, v in kwargs.items():
            if isinstance(v, (str, int, float)):
                safe_kwargs[k] = v
            else:
                safe_kwargs[k] = str(v)

        try:
            return template.format(**safe_kwargs)
        except KeyError:
            # If format fails, return template as-is
            return template


# Singleton instance
_i18n_service: I18nService | None = None


def get_i18n_service() -> I18nService:
    """
    Get the singleton I18nService instance.

    Returns:
        I18nService instance
    """
    global _i18n_service
    if _i18n_service is None:
        _i18n_service = I18nService()
    return _i18n_service


__all__ = [
    "I18nService",
    "get_i18n_service",
    "LanguageCode",
    "LANGUAGES",
    "DEFAULT_LANGUAGE",
]
