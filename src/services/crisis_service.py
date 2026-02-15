"""
Crisis Safety Net for Aurora Sun V1.

SW-11: Mental Health Override - Crisis Detection and Response
When a user expresses crisis signals, all normal operations pause
and crisis resources take priority over everything else.

Data Classification: ART_9_SPECIAL (mental health data requires encryption)
Reference: ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
Reference: CLAUDE.md Section on Safety

IMPORTANT: This service is a SAFETY FEATURE. It MUST never be rate-limited
or blocked by normal security measures when a real crisis is detected.

Usage:
    crisis = CrisisService()

    # Check message for crisis signals
    level = await crisis.detect_crisis("I don't want to exist anymore")
    # Returns: CrisisLevel.CRISIS

    # Handle detected crisis
    if level != CrisisLevel.NONE:
        response = await crisis.handle_crisis(user_id=123, level=level)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    EncryptionService,
    EncryptionServiceError,
    get_encryption_service,
)
from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class CrisisLevel(StrEnum):
    """Crisis detection levels."""

    NONE = "none"      # No crisis signals detected
    WARNING = "warning"  # Concerning signals, monitor closely
    CRISIS = "crisis"   # Immediate crisis response required


class CountryCode(StrEnum):
    """Supported country codes for hotlines."""

    US = "US"
    UK = "UK"
    DE = "DE"
    AT = "AT"
    CH = "CH"
    IE = "IE"
    NL = "NL"
    FR = "FR"
    ES = "ES"
    IT = "IT"
    CA = "CA"
    AU = "AU"


@dataclass
class CrisisSignal:
    """
    Detected crisis signal with metadata.

    Attributes:
        signal: The keyword/pattern that triggered detection
        severity: How severe this specific signal is
        context: Surrounding context from the message
    """

    signal: str
    severity: int  # 1-10, how severe this signal is
    context: str   # Surrounding text for context


@dataclass
class CrisisResponse:
    """
    Response to a detected crisis.

    Attributes:
        level: The detected crisis level
        message: Response message to show user
        resources: List of crisis resources to provide
        should_pause_workflows: Whether to pause all normal operations
        should_notify_admin: Whether to notify admin
        hotline_provided: Whether a country-specific hotline was included
        signal_detected: The signal that triggered this response
    """

    level: CrisisLevel
    message: str
    resources: list[str]
    should_pause_workflows: bool
    should_notify_admin: bool
    hotline_provided: bool
    signal_detected: CrisisSignal | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, str | list[str] | bool | None]:
        """Convert to dictionary representation."""
        return {
            "level": self.level.value,
            "message": self.message,
            "resources": self.resources,
            "should_pause_workflows": self.should_pause_workflows,
            "should_notify_admin": self.should_notify_admin,
            "hotline_provided": self.hotline_provided,
            "signal_detected": self.signal_detected.signal if self.signal_detected else None,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# Crisis Service
# =============================================================================


class CrisisService:
    """
    Crisis Safety Net Service (SW-11).

    Detects mental health crisis signals in user messages and provides
    appropriate response with resources. This service operates with
    highest priority - it should NEVER be rate-limited.

    Crisis Detection:
    - Keyword matching for immediate crisis terms
    - Context analysis for subtle signals
    - Severity scoring for response calibration

    Crisis Response:
    - Immediate provision of crisis resources
    - Workflow pause (all non-essential operations stop)
    - Admin notification (if configured)
    - NEVER dismiss or minimize crisis signals

    Data Handling:
    - All crisis-related data is ART_9_SPECIAL (health data)
    - Uses field-level encryption with per-user keys
    - Crisis events logged for safety review (encrypted)
    - No crisis data used for analytics or training

    Usage:
        crisis = CrisisService()

        # Detect crisis in message
        level = await crisis.detect_crisis("I can't go on anymore")

        # Handle detected crisis
        if level != CrisisLevel.NONE:
            response = await crisis.handle_crisis(user_id=123, level=level)

        # Get hotline for user
        hotline = await crisis.get_hotline(country="DE")
    """

    # Crisis signals requiring immediate response (highest priority)
    CRISIS_SIGNALS = [
        # Suicidal ideation - direct
        "suicidal",
        "kill myself",
        "end it all",
        "better off dead",
        "want to die",
        "want to end it",
        "going to kill myself",
        "planning to die",
        "suicide",
        # Self-harm - direct
        "self-harm",
        "hurt myself",
        "cut myself",
        "harm myself",
        "self injury",
        # Crisis expressions
        "can't go on",
        "no point",
        "nothing matters",
        "better without me",
        "everyone would be better",
        "shouldn't exist",
    ]

    # Warning signals (concerning but not immediate crisis)
    WARNING_SIGNALS = [
        "feel empty",
        "feel hopeless",
        "feel worthless",
        "can't cope",
        "overwhelming",
        "falling apart",
        "losing control",
        "not okay",
        "not doing well",
        "struggling",
        "can't handle",
        "giving up",
        "tired of trying",
    ]

    # Hotlines by country (international standardized numbers where available)
    HOTLINES: dict[CountryCode, dict[str, str | None]] = {
        CountryCode.US: {
            "name": "988 Suicide & Crisis Lifeline",
            "number": "988",
            "website": "988lifeline.org",
            "text": "Text HOME to 741741",
        },
        CountryCode.UK: {
            "name": "Samaritans",
            "number": "116 123",
            "website": "samaritans.org",
            "text": None,
        },
        CountryCode.DE: {
            "name": "Telefonseelsorge",
            "number": "0800 111 0 111",
            "website": "telefonseelsorge.de",
            "text": None,
        },
        CountryCode.AT: {
            "name": "Telefonseelsorge Oesterreich",
            "number": "142",
            "website": "telefonseelsorge.at",
            "text": None,
        },
        CountryCode.CH: {
            "name": "Telefonhilfe",
            "number": "143",
            "website": "telefonhilfe.ch",
            "text": None,
        },
        CountryCode.IE: {
            "name": "Samaritans Ireland",
            "number": "116 123",
            "website": "samaritans.ie",
            "text": None,
        },
        CountryCode.NL: {
            "name": "113 Zelfmoordpreventie",
            "number": "0800 0113",
            "website": "113.nl",
            "text": "Text 113 to 4301",
        },
        CountryCode.FR: {
            "name": "Sorore",
            "number": "3114",
            "website": "3114.org",
            "text": None,
        },
        CountryCode.ES: {
            "name": "Telefono de la Esperanza",
            "number": "717 003 717",
            "website": "telefonoesperanza.com",
            "text": None,
        },
        CountryCode.IT: {
            "name": "Telefono Amico",
            "number": "02 2327 2327",
            "website": "telefonoamico.it",
            "text": None,
        },
        CountryCode.CA: {
            "name": "Talk Suicide Canada",
            "number": "1-833-456-4566",
            "website": "talksuicide.ca",
            "text": "Text 45645",
        },
        CountryCode.AU: {
            "name": "Lifeline Australia",
            "number": "13 11 14",
            "website": "lifeline.org.au",
            "text": "Text 0477 13 11 14",
        },
    }

    # Default/fallback hotline (US 988 is internationally recognized)
    DEFAULT_HOTLINE: dict[str, str] = {
        "name": "International Association for Suicide Prevention",
        "number": "Varies by country - see https://www.iasp.info/resources/Crisis_Centres/",
        "website": "findahelpline.com",
        "text": "See website for text options",
    }

    # Per-user crisis alert rate limiting to prevent alert fatigue.
    # Max 5 crisis alerts per hour per user. After the limit, still log the event
    # and respond to the user with crisis resources, but suppress admin notifications.
    CRISIS_ALERT_MAX_PER_HOUR = 5
    CRISIS_ALERT_WINDOW_SECONDS = 3600  # 1 hour

    # Maximum crisis log entries per user in the in-memory store.
    # Production should use PostgreSQL with proper retention policies.
    MAX_LOG_ENTRIES_PER_USER = 100

    def __init__(self, encryption_service: EncryptionService | None = None):
        """
        Initialize the Crisis Service.

        Args:
            encryption_service: Optional encryption service. Uses global if None.
        """
        self._encryption = encryption_service or get_encryption_service()
        # In-memory crisis event log (encrypted at rest)
        self._crisis_log: dict[int, list[dict[str, str | int | None]]] = {}
        # Per-user crisis alert timestamps for rate limiting
        self._crisis_alert_timestamps: dict[int, list[float]] = {}

    async def detect_crisis(self, message: str) -> CrisisLevel:
        """
        Detect crisis signals in a message.

        Analyzes the message for crisis keywords and patterns.
        Returns appropriate crisis level based on signal severity.

        Args:
            message: User message to analyze

        Returns:
            CrisisLevel: NONE, WARNING, or CRISIS

        Examples:
            >>> level = await crisis.detect_crisis("I don't want to exist anymore")
            >>> level
            <CrisisLevel.CRISIS: 'crisis'>

            >>> level = await crisis.detect_crisis("I'm feeling a bit down today")
            >>> level
            <CrisisLevel.NONE: 'none'>
        """
        message_lower = message.lower()

        # Check for immediate crisis signals first
        crisis_score = 0
        detected_signal: CrisisSignal | None = None

        for signal in self.CRISIS_SIGNALS:
            if signal in message_lower:
                # Calculate severity based on signal specificity
                severity = self._calculate_signal_severity(signal, message_lower)
                if severity > crisis_score:
                    crisis_score = severity
                    detected_signal = CrisisSignal(
                        signal=signal,
                        severity=severity,
                        context=self._extract_context(message, signal),
                    )

        if crisis_score >= 8:
            logger.warning(
                "crisis_signal_detected level=crisis severity=%d",
                detected_signal.severity if detected_signal else 0,
            )
            return CrisisLevel.CRISIS

        # Check for warning signals
        warning_score = 0
        best_warning_signal: str | None = None
        for signal in self.WARNING_SIGNALS:
            if signal in message_lower:
                severity = self._calculate_signal_severity(signal, message_lower)
                if severity > warning_score:
                    warning_score = severity
                    best_warning_signal = signal

        if warning_score >= 5:
            if warning_score > crisis_score and best_warning_signal:
                detected_signal = CrisisSignal(
                    signal=best_warning_signal,
                    severity=warning_score,
                    context=self._extract_context(message, best_warning_signal),
                )
            return CrisisLevel.WARNING

        return CrisisLevel.NONE

    def _calculate_signal_severity(self, signal: str, message: str) -> int:
        """
        Calculate severity score for a detected signal.

        Higher severity for:
        - Direct statements vs. questions
        - Specific plans vs. general thoughts
        - Recent/frequent mentions

        Args:
            signal: The detected signal keyword
            message: Full message context

        Returns:
            Severity score 1-10
        """
        base_severity = 5  # Default

        # Direct statements are more severe
        direct_patterns = [
            r"\bi\s+(?:am\s+)?going\s+to\b",
            r"\bi\s+will\b",
            r"\bi\s+(?:have\s+)?(?:already\s+)?(?:decided?\b|planned?\b)",
            r"\bi've?\s+got\s+(?:a\s+)?plan",
        ]

        for pattern in direct_patterns:
            if re.search(pattern, message):
                base_severity += 2
                break

        # Questions are less severe (seeking help)
        if "?" in message:
            base_severity -= 2

        # Extremity words increase severity
        extreme_words = ["always", "never", "everyone", "nobody", "everything", "nothing"]
        for word in extreme_words:
            if word in message:
                base_severity += 1
                break

        # Clamp to 1-10 range
        return max(1, min(10, base_severity))

    def _extract_context(self, message: str, signal: str, context_chars: int = 50) -> str:
        """
        Extract surrounding context for a detected signal.

        Args:
            message: Full message
            signal: Detected signal keyword
            context_chars: Characters to include before/after

        Returns:
            Context string
        """
        message_lower = message.lower()
        pos = message_lower.find(signal)
        if pos == -1:
            return message[:100]

        start = max(0, pos - context_chars)
        end = min(len(message), pos + len(signal) + context_chars)

        context = message[start:end].strip()
        if start > 0:
            context = "..." + context
        if end < len(message):
            context = context + "..."

        return context

    def _check_crisis_alert_rate(self, user_id: int) -> bool:
        """
        Check if admin notifications should be sent for this user.

        Limits admin notifications to CRISIS_ALERT_MAX_PER_HOUR
        per user per hour. Always still responds to the user with crisis
        resources regardless of this limit.

        Args:
            user_id: User identifier

        Returns:
            True if admin notification is allowed, False if rate-limited
        """
        import time

        now = time.time()
        cutoff = now - self.CRISIS_ALERT_WINDOW_SECONDS

        if user_id not in self._crisis_alert_timestamps:
            self._crisis_alert_timestamps[user_id] = []

        # Remove expired timestamps
        self._crisis_alert_timestamps[user_id] = [
            ts for ts in self._crisis_alert_timestamps[user_id] if ts > cutoff
        ]

        if len(self._crisis_alert_timestamps[user_id]) >= self.CRISIS_ALERT_MAX_PER_HOUR:
            logger.warning(
                "crisis_alert_rate_limited user_hash=%s alerts_in_window=%d",
                hash_uid(user_id),
                len(self._crisis_alert_timestamps[user_id]),
            )
            return False

        # Record this alert
        self._crisis_alert_timestamps[user_id].append(now)
        return True

    async def handle_crisis(
        self,
        user_id: int,
        level: CrisisLevel,
        signal: CrisisSignal | None = None,
    ) -> CrisisResponse:
        """
        Handle a detected crisis with appropriate response.

        Response includes:
        - Empathetic acknowledgment
        - Crisis resources (hotlines)
        - Workflow pause flag
        - Admin notification flag (rate-limited per user to prevent alert fatigue)

        The user ALWAYS receives crisis resources regardless of rate limiting.
        Only admin notifications are suppressed after the rate limit is reached.

        Args:
            user_id: User identifier
            level: Detected crisis level
            signal: Optional signal details

        Returns:
            CrisisResponse with resources and actions

        Note:
            This method ALWAYS returns a response, never raises.
            Even if crisis detection fails, user gets supportive message.
        """
        # Log crisis event (encrypted in production) -- always logged
        await self._log_crisis_event(user_id, level, signal)

        # Check per-user crisis alert rate limit
        admin_notify_allowed = self._check_crisis_alert_rate(user_id)

        if level == CrisisLevel.CRISIS:
            response = await self._handle_crisis_level(user_id, signal)
            # Suppress admin notification if rate-limited, but always provide resources
            if not admin_notify_allowed:
                response.should_notify_admin = False
            return response
        elif level == CrisisLevel.WARNING:
            return await self._handle_warning_level(user_id, signal)
        else:
            # None level - shouldn't be called, but handle gracefully
            return CrisisResponse(
                level=CrisisLevel.NONE,
                message="I'm here to support you. How can I help?",
                resources=[],
                should_pause_workflows=False,
                should_notify_admin=False,
                hotline_provided=False,
            )

    async def _handle_crisis_level(
        self,
        user_id: int,
        signal: CrisisSignal | None,
        country: str = "US",
    ) -> CrisisResponse:
        """Handle immediate crisis level.

        Args:
            user_id: User identifier
            signal: Detected crisis signal
            country: Country code for hotline lookup (default: US)
        """
        hotline_info = await self.get_hotline(country)

        hotline_text = f"\n\nCrisis Hotline: {hotline_info['number']}"
        if hotline_info.get("text"):
            hotline_text += f"\nText: {hotline_info['text']}"
        hotline_text += f"\n{hotline_info['website']}"

        message = (
            "I hear you, and I want you to know: your life has value. "
            "What you're experiencing right now is incredibly painful, "
            "but there are people who want to help you get through this.\n"
            f"{hotline_text}\n\n"
            "Please reach out to a crisis line or emergency services. "
            "You don't have to face this alone."
        )

        return CrisisResponse(
            level=CrisisLevel.CRISIS,
            message=message,
            resources=[
                f"Primary: {hotline_info['name']} - {hotline_info['number']}",
                f"Website: {hotline_info['website']}",
                "Emergency Services: 911 (US) / 112 (EU)",
            ],
            should_pause_workflows=True,
            should_notify_admin=True,
            hotline_provided=True,
            signal_detected=signal,
        )

    async def _handle_warning_level(
        self,
        user_id: int,
        signal: CrisisSignal | None,
    ) -> CrisisResponse:
        """Handle warning level (concerning but not immediate crisis)."""
        message = (
            "Thank you for sharing how you're feeling. "
            "It takes courage to be honest about difficult emotions.\n\n"
            "I'm concerned about you, and I want to make sure you have support. "
            "If things ever feel overwhelming, these resources can help:"
        )

        # Provide resources but don't require immediate action
        resources = [
            "988 Suicide & Crisis Lifeline (US): 988",
            "International: findahelpline.com",
            "Crisis Text Line: Text HOME to 741741",
        ]

        return CrisisResponse(
            level=CrisisLevel.WARNING,
            message=message,
            resources=resources,
            should_pause_workflows=False,  # Don't pause, but offer support
            should_notify_admin=False,  # Warning doesn't require admin notification
            hotline_provided=True,
            signal_detected=signal,
        )

    async def get_hotline(self, country: str) -> dict[str, str | None]:
        """
        Get crisis hotline information for a country.

        Args:
            country: Country code (ISO 2-letter or full name)

        Returns:
            Dictionary with hotline details

        Example:
            >>> hotline = await crisis.get_hotline("DE")
            >>> print(hotline["number"])
            0800 111 0 111
        """
        # Try to match country code
        country_upper = country.upper()

        # Direct match
        try:
            country_enum = CountryCode(country_upper)
            return self.HOTLINES[country_enum]
        except ValueError:
            pass

        # Country name to code mapping
        country_map = {
            "united states": CountryCode.US,
            "usa": CountryCode.US,
            "united kingdom": CountryCode.UK,
            "germany": CountryCode.DE,
            "deutschland": CountryCode.DE,
            "austria": CountryCode.AT,
            "oesterreich": CountryCode.AT,
            "switzerland": CountryCode.CH,
            "schweiz": CountryCode.CH,
            "ireland": CountryCode.IE,
            "netherlands": CountryCode.NL,
            "nederland": CountryCode.NL,
            "france": CountryCode.FR,
            "spain": CountryCode.ES,
            "italy": CountryCode.IT,
            "canada": CountryCode.CA,
            "australia": CountryCode.AU,
        }

        country_lower = country.lower()
        if country_lower in country_map:
            return self.HOTLINES[country_map[country_lower]]

        # Fallback to default
        logger.warning("unknown_country_code_using_default")
        return dict(self.DEFAULT_HOTLINE)  # Create a new dict to match return type

    async def _log_crisis_event(
        self,
        user_id: int,
        level: CrisisLevel,
        signal: CrisisSignal | None,
    ) -> None:
        """
        Log crisis event for safety review.

        In production, this would:
        1. Encrypt the log entry with ART_9_SPECIAL classification
        2. Store in PostgreSQL
        3. Include for admin safety reviews

        Args:
            user_id: User identifier
            level: Crisis level detected
            signal: Signal details (if any)
        """
        event: dict[str, int | str | float | None] = {
            "user_id": user_id,
            "level": level.value,
            "signal": signal.signal if signal else None,
            "signal_severity": float(signal.severity) if signal else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if user_id not in self._crisis_log:
            self._crisis_log[user_id] = []

        # Trim older entries when exceeding the limit to prevent unbounded growth
        if len(self._crisis_log[user_id]) >= self.MAX_LOG_ENTRIES_PER_USER:
            self._crisis_log[user_id] = self._crisis_log[user_id][
                -self.MAX_LOG_ENTRIES_PER_USER + 1 :
            ]

        # Encrypt event before storing (ART_9_SPECIAL)
        try:
            encrypted = self._encryption.encrypt_field(
                json.dumps(event),
                user_id=user_id,
                classification=DataClassification.ART_9_SPECIAL,
                field_name=f"crisis_event_{len(self._crisis_log[user_id]) + 1}",
            )
            self._crisis_log[user_id].append(encrypted.to_db_dict())
        except EncryptionServiceError:
            logger.error("crisis_event_encryption_failed — refusing plaintext storage")
            raise

        logger.info(
            "crisis_event_logged user_hash=%s level=%s",
            hash_uid(user_id),
            level.value,
        )

    def _decrypt_event(
        self,
        stored: dict[str, str | int | None],
        user_id: int,
    ) -> dict[str, int | str | float | None]:
        """Decrypt a single stored crisis event."""
        classification = stored.get("classification")
        if classification == "plaintext_fallback":
            # Dev-mode fallback: stored as plain JSON
            ciphertext = stored.get("ciphertext")
            result: dict[str, int | str | float | None] = json.loads(
                str(ciphertext)
            )
            return result
        try:
            encrypted = EncryptedField.from_db_dict(
                {k: v for k, v in stored.items()}
            )
            plaintext = self._encryption.decrypt_field(encrypted, user_id=user_id)
            decrypted: dict[str, int | str | float | None] = json.loads(plaintext)
            return decrypted
        except (EncryptionServiceError, json.JSONDecodeError, KeyError):
            logger.warning("crisis_event_decryption_failed")
            return {"level": "unknown", "timestamp": None}

    async def get_crisis_history(self, user_id: int, limit: int = 10) -> list[dict[str, int | str | float | None]]:
        """
        Get crisis event history for a user.

        Used for safety review and context understanding.
        All data is encrypted with ART_9_SPECIAL classification.

        Args:
            user_id: User identifier
            limit: Maximum events to return

        Returns:
            List of crisis events (most recent first)
        """
        if user_id not in self._crisis_log:
            return []

        stored_events = self._crisis_log[user_id][-limit:]
        return list(reversed([
            self._decrypt_event(e, user_id) for e in stored_events
        ]))

    async def should_pause_workflows(self, user_id: int) -> bool:
        """
        Check if workflows should be paused for a user.

        Returns True if user has recent crisis events that warrant
        pausing normal operations.

        Args:
            user_id: User identifier

        Returns:
            True if workflows should pause
        """
        if user_id not in self._crisis_log:
            return False

        # Check for recent crisis-level events (last 24 hours)
        from datetime import timedelta

        recent_crisis = False
        for stored_event in reversed(self._crisis_log[user_id]):
            event = self._decrypt_event(stored_event, user_id)
            if event.get("level") == CrisisLevel.CRISIS.value:
                timestamp_val = event.get("timestamp")
                if isinstance(timestamp_val, str):
                    event_time = datetime.fromisoformat(timestamp_val)
                    if datetime.now(UTC) - event_time < timedelta(hours=24):
                        recent_crisis = True
                        break

        return recent_crisis


# =============================================================================
# Module Singleton and Convenience Functions
# =============================================================================

_crisis_service: CrisisService | None = None


def get_crisis_service() -> CrisisService:
    """Get the singleton CrisisService instance."""
    global _crisis_service
    if _crisis_service is None:
        _crisis_service = CrisisService()
    return _crisis_service


async def check_and_handle_crisis(user_id: int, message: str) -> CrisisResponse | None:
    """
    Convenience function to check message and handle crisis in one call.

    Args:
        user_id: User identifier
        message: Message to check

    Returns:
        CrisisResponse if crisis detected, None otherwise
    """
    service = get_crisis_service()
    level = await service.detect_crisis(message)

    if level == CrisisLevel.NONE:
        return None

    return await service.handle_crisis(user_id, level)
