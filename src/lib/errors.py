"""
Centralized Error Response Builder for Aurora Sun V1.

Provides consistent error codes, messages, and i18n-ready error responses
for use across API, webhook, and service layers.

Error codes are constants that map to translatable message strings.
The builder returns structured error dicts compatible with the API
response envelope (ResponseEnvelope).

Reference: REFACTOR-011, ARCHITECTURE.md Section 14
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Error Code Constants
# =============================================================================

AUTH_REQUIRED = "AUTH_REQUIRED"
RATE_LIMITED = "RATE_LIMITED"
NOT_FOUND = "NOT_FOUND"
VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
FORBIDDEN = "FORBIDDEN"
CONSENT_REQUIRED = "CONSENT_REQUIRED"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

# =============================================================================
# i18n Message Registry
#
# Maps (error_code, language) -> translated message string.
# Extend this dict to add new languages. Falls back to "en" if a
# translation is missing for the requested language.
# =============================================================================

_ERROR_MESSAGES: dict[str, dict[str, str]] = {
    AUTH_REQUIRED: {
        "en": "Authentication is required.",
        "de": "Authentifizierung erforderlich.",
        "sr": "Potrebna je autentifikacija.",
        "el": "Apaiteitai pistopoiisi.",
    },
    RATE_LIMITED: {
        "en": "Too many requests. Please try again later.",
        "de": "Zu viele Anfragen. Bitte versuche es spaeter erneut.",
        "sr": "Previse zahteva. Pokusajte ponovo kasnije.",
        "el": "Polla aitimata. Dokimaste xana argotera.",
    },
    NOT_FOUND: {
        "en": "The requested resource was not found.",
        "de": "Die angeforderte Ressource wurde nicht gefunden.",
        "sr": "Trazeni resurs nije pronadjen.",
        "el": "O zitoumenos poros den vrethike.",
    },
    VALIDATION_ERROR: {
        "en": "Invalid input. Please check your request.",
        "de": "Ungueltige Eingabe. Bitte ueberpruefen Sie Ihre Anfrage.",
        "sr": "Nevazeci unos. Proverite vas zahtev.",
        "el": "Mi egkyri eisagogi. Elegxte to aitima sas.",
    },
    INTERNAL_ERROR: {
        "en": "An internal error occurred. Please try again.",
        "de": "Ein interner Fehler ist aufgetreten. Bitte erneut versuchen.",
        "sr": "Doslo je do interne greske. Pokusajte ponovo.",
        "el": "Proekypse esoteriko sfalma. Dokimaste xana.",
    },
    FORBIDDEN: {
        "en": "You do not have permission to perform this action.",
        "de": "Sie haben keine Berechtigung fuer diese Aktion.",
        "sr": "Nemate dozvolu za ovu akciju.",
        "el": "Den echete adeia gia afti tin energeia.",
    },
    CONSENT_REQUIRED: {
        "en": "Consent is required before processing your data.",
        "de": "Ihre Zustimmung ist erforderlich, bevor wir Ihre Daten verarbeiten.",
        "sr": "Potrebna je saglasnost pre obrade vasih podataka.",
        "el": "Apaiteitai synainesi prin tin epexergasia ton dedomenon sas.",
    },
    NOT_IMPLEMENTED: {
        "en": "This feature is not yet implemented.",
        "de": "Diese Funktion ist noch nicht implementiert.",
        "sr": "Ova funkcija jos nije implementirana.",
        "el": "Afti i leitourgia den echei ylopoiithei akomi.",
    },
}

# Default fallback language
_DEFAULT_LANG = "en"


# =============================================================================
# Error Response Builder
# =============================================================================


def get_error_message(code: str, lang: str = "en") -> str:
    """
    Get a translated error message for a given error code.

    Falls back to English if the requested language is not available.
    Falls back to a generic message if the error code is unknown.

    Args:
        code: Error code constant (e.g. AUTH_REQUIRED, NOT_FOUND)
        lang: ISO 639-1 language code (e.g. "en", "de", "sr", "el")

    Returns:
        Translated error message string
    """
    messages = _ERROR_MESSAGES.get(code, {})
    return messages.get(lang, messages.get(_DEFAULT_LANG, "An error occurred."))


def build_error_response(
    code: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    """
    Build a structured error response dict.

    The returned dict is compatible with the API ResponseEnvelope error field:
    { "code": "...", "message": "..." }

    If no message is provided, the i18n-translated message for the error code
    and language is used automatically.

    Args:
        code: Error code constant (e.g. AUTH_REQUIRED, NOT_FOUND)
        message: Optional override message (bypasses i18n lookup)
        details: Optional additional error details
        lang: ISO 639-1 language code for i18n message lookup

    Returns:
        Structured error dict: {"code": str, "message": str, "details": dict | None}
    """
    resolved_message = message if message is not None else get_error_message(code, lang)
    error: dict[str, Any] = {
        "code": code,
        "message": resolved_message,
    }
    if details is not None:
        error["details"] = details
    return error


__all__ = [
    # Error code constants
    "AUTH_REQUIRED",
    "RATE_LIMITED",
    "NOT_FOUND",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "FORBIDDEN",
    "CONSENT_REQUIRED",
    "NOT_IMPLEMENTED",
    # Functions
    "get_error_message",
    "build_error_response",
]
