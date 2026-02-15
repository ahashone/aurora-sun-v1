"""
Onboarding Flow for Aurora Sun V1.

Implements SW-13: User Onboarding

Flow States:
    1. LANGUAGE - Auto-detected from Telegram, can be changed
    2. NAME - Capture user's preferred name
    3. WORKING_STYLE - Infer or ask for neurotype segment
    4. CONSENT - Explicit consent gate (not skippable, GDPR Art. 9)
    5. CONFIRMATION - Onboarding complete, ready for daily workflow

References:
    - ARCHITECTURE.md Section 13 (SW-13: User Onboarding)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
    - ARCHITECTURE.md Section 3 (Neurotype Segmentation)
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from src.lib.encryption import hash_telegram_id
from src.services.redis_service import get_redis_service

logger = logging.getLogger(__name__)

# Redis key prefixes and TTL for onboarding state
_ONBOARDING_STATE_PREFIX = "aurora:onboarding:state:"
_ONBOARDING_DATA_PREFIX = "aurora:onboarding:data:"
_ONBOARDING_TTL = 3600  # 1 hour TTL for onboarding state


# =============================================================================
# Onboarding States
# =============================================================================


class OnboardingStates(StrEnum):
    """Onboarding state machine states."""

    LANGUAGE = "language"           # Language selection
    NAME = "name"                  # Name capture
    WORKING_STYLE = "working_style"  # Segment selection
    CONSENT = "consent"            # GDPR consent gate
    CONFIRMATION = "confirmation"  # Onboarding complete
    COMPLETED = "completed"        # User is onboarded


# Valid state transitions. Each state maps to its allowed next states.
VALID_TRANSITIONS: dict[OnboardingStates, set[OnboardingStates]] = {
    OnboardingStates.LANGUAGE: {OnboardingStates.NAME},
    OnboardingStates.NAME: {OnboardingStates.WORKING_STYLE},
    OnboardingStates.WORKING_STYLE: {OnboardingStates.CONSENT},
    OnboardingStates.CONSENT: {OnboardingStates.CONFIRMATION, OnboardingStates.COMPLETED},
    OnboardingStates.CONFIRMATION: {OnboardingStates.COMPLETED},
    OnboardingStates.COMPLETED: set(),  # Terminal state
}

# Exact set of allowed callback values. No startswith() parsing (prevents injection).
ALLOWED_CALLBACKS: set[str] = {
    "lang_en", "lang_de", "lang_sr", "lang_el",
    "segment_AD", "segment_AU", "segment_AH", "segment_NT", "segment_CU",
    "consent_accept", "consent_reject",
}


# Segment display names (user-facing)
SEGMENT_DISPLAY_NAMES = {
    "AD": "ADHD",
    "AU": "Autism",
    "AH": "AuDHD",
    "NT": "Neurotypical",
    "CU": "Custom",
}

SEGMENT_CODES = list(SEGMENT_DISPLAY_NAMES.keys())

# =============================================================================
# Consent Text Translations
# =============================================================================


CONSENT_TEXTS = {
    "en": """
I agree to the processing of my personal data for the purpose of AI coaching.

Data processed:
- My messages and reflections
- My goals and tasks
- My energy and mood (if shared)

Your data is:
- Encrypted at rest (AES-256)
- Processed by AI services (see /privacy for details)
- Stored in EU/Germany
- Deletable at any time

You can withdraw consent anytime by typing "/delete".
""",
    "de": """
Ich stimme der Verarbeitung meiner personenbezogenen Daten zum Zweck des KI-Coachings zu.

Verarbeitete Daten:
- Meine Nachrichten und Reflexionen
- Meine Ziele und Aufgaben
- Meine Energie und Stimmung (falls geteilt)

Ihre Daten sind:
- Verschluesselt gespeichert (AES-256)
- Verarbeitet durch KI-Dienste (siehe /privacy fuer Details)
- In der EU/Deutschland gespeichert
- Jederzeit loeschbar

Sie koennen die Einwilligung jederzeit widerrufen mit "/delete".
""",
    "sr": """
Saglasan sam sa obradom mojih licnih podataka u svrhu AI coachiranja.

Obradjeni podaci:
- Moje poruke i refleksije
- Moji ciljevi i zadaci
- Moja energija i raspolozenje (ako podelim)

Vasi podaci su:
- Sifrovani u mirovanju (AES-256)
- Obradjivani od strane AI servisa (pogledajte /privacy za detalje)
- Cuvaju se u EU/Nemackoj
- Mogu se izbrisati u bilo kom trenutku

Mozete povuci saglasnost u bilo kom trenutku pisanjem "/delete".
""",
    "el": """
Συμφωνώ με την επεξεργασία των προσωπικών μου δεδομένων για σκοπούς AI coaching.

Επεξεργασμένα δεδομένα:
- Τα μηνύματα και οι αναστοχασμοί μου
- Οι στόχοι και οι εργασίες μου
- Η ενέργεια και η διάθεσή μου (αν μοιραστώ)

Τα δεδομένα σας είναι:
- Κρυπτογραφημένα σε κατάσταση ηρεμίας (AES-256)
- Επεξεργάζονται από υπηρεσίες AI (δείτε /privacy για λεπτομέρειες)
- Αποθηκεύονται στην ΕΕ/Γερμανία
- Διαγράψιμα ανά πάσα στιγμή

Μπορείτε να αποσύρετε τη συγκατάθεσή σας ανά πάσα στιγμή γράφοντας "/delete".
""",
}

DEFAULT_LANGUAGE = "en"


# =============================================================================
# Onboarding Flow Class
# =============================================================================


@dataclass
class OnboardingStep:
    """Represents a single step in the onboarding flow."""

    state: OnboardingStates
    prompt_key: str
    keyboard: Callable[[str], list[list[InlineKeyboardButton]]] | None = None
    validator: Callable[[str], bool] | None = None
    transformer: Callable[[str], str] | None = None


class OnboardingFlow:
    """
    Onboarding state machine for new users.

    Implements SW-13: User Onboarding with the following steps:
    1. Language selection (auto-detected from Telegram, can be changed)
    2. Name capture
    3. Working style (segment) inference/selection
    4. CONSENT GATE (explicit, not skippable - GDPR Art. 9)
    5. Confirmation

    Key Principles:
    - Consent gate is NOT skippable
    - All text is translated
    - Segment selection uses display names, not internal codes
    """

    def __init__(self) -> None:
        """Initialize the onboarding flow."""
        # In-memory fallback when Redis is unavailable
        self._states_fallback: dict[str, OnboardingStates] = {}
        self._user_data_fallback: dict[str, dict[str, Any]] = {}
        self._redis = get_redis_service()

        # Define onboarding steps
        self._steps: list[OnboardingStep] = [
            OnboardingStep(
                state=OnboardingStates.LANGUAGE,
                prompt_key="select_language",
                keyboard=self._language_keyboard,
            ),
            OnboardingStep(
                state=OnboardingStates.NAME,
                prompt_key="enter_name",
                validator=self._validate_name,
                transformer=self._transform_name,
            ),
            OnboardingStep(
                state=OnboardingStates.WORKING_STYLE,
                prompt_key="select_style",
                keyboard=self._segment_keyboard,
            ),
            OnboardingStep(
                state=OnboardingStates.CONSENT,
                prompt_key="consent",
                keyboard=self._consent_keyboard,
            ),
            OnboardingStep(
                state=OnboardingStates.CONFIRMATION,
                prompt_key="confirmation",
            ),
        ]

    # =========================================================================
    # State persistence (Redis with in-memory fallback)
    # =========================================================================

    async def _get_state(self, user_hash: str) -> OnboardingStates | None:
        """Get onboarding state from Redis, falling back to memory."""
        try:
            value = await self._redis.get(f"{_ONBOARDING_STATE_PREFIX}{user_hash}")
            if value is not None:
                return OnboardingStates(value.strip('"'))
        except Exception as e:
            logger.warning(
                "Redis get failed for onboarding state, using memory fallback",
                extra={"user_hash": user_hash[:8], "error": type(e).__name__},
            )
        return self._states_fallback.get(user_hash)

    async def _set_state(self, user_hash: str, state: OnboardingStates) -> None:
        """Persist onboarding state to Redis with in-memory fallback."""
        self._states_fallback[user_hash] = state
        try:
            await self._redis.set(
                f"{_ONBOARDING_STATE_PREFIX}{user_hash}",
                state.value,
                ttl=_ONBOARDING_TTL,
            )
        except Exception as e:
            logger.warning(
                "Redis set failed for onboarding state, using memory fallback only",
                extra={"user_hash": user_hash[:8], "state": state.value, "error": type(e).__name__},
            )

    async def _get_data(self, user_hash: str) -> dict[str, Any]:
        """Get onboarding user data from Redis, falling back to memory."""
        try:
            raw = await self._redis.get(f"{_ONBOARDING_DATA_PREFIX}{user_hash}")
            if raw is not None:
                data: dict[str, Any] = json.loads(raw)
                return data
        except Exception as e:
            logger.warning(
                "Redis get failed for onboarding data, using memory fallback",
                extra={"user_hash": user_hash[:8], "error": type(e).__name__},
            )
        return self._user_data_fallback.get(user_hash, {})

    async def _set_data(self, user_hash: str, data: dict[str, Any]) -> None:
        """Persist onboarding user data to Redis with in-memory fallback."""
        self._user_data_fallback[user_hash] = data
        try:
            await self._redis.set(
                f"{_ONBOARDING_DATA_PREFIX}{user_hash}",
                data,
                ttl=_ONBOARDING_TTL,
            )
        except Exception as e:
            logger.warning(
                "Redis set failed for onboarding data, using memory fallback only",
                extra={"user_hash": user_hash[:8], "error": type(e).__name__},
            )

    def _language_keyboard(self, language: str = "en") -> list[list[InlineKeyboardButton]]:
        """Generate language selection keyboard."""
        return [
            [InlineKeyboardButton("English", callback_data="lang_en")],
            [InlineKeyboardButton("Deutsch", callback_data="lang_de")],
            [InlineKeyboardButton("Srpski", callback_data="lang_sr")],
            [InlineKeyboardButton("Ελληνικά", callback_data="lang_el")],
        ]

    def _segment_keyboard(self, language: str = "en") -> list[list[InlineKeyboardButton]]:
        """Generate segment selection keyboard."""
        return [
            [InlineKeyboardButton("ADHD", callback_data="segment_AD")],
            [InlineKeyboardButton("Autism", callback_data="segment_AU")],
            [InlineKeyboardButton("AuDHD", callback_data="segment_AH")],
            [InlineKeyboardButton("Neurotypical", callback_data="segment_NT")],
            [InlineKeyboardButton("Custom", callback_data="segment_CU")],
        ]

    def _consent_keyboard(self, language: str = "en") -> list[list[InlineKeyboardButton]]:
        """Generate consent acceptance keyboard."""
        return [
            [InlineKeyboardButton("I Agree", callback_data="consent_accept")],
            [InlineKeyboardButton("I Do Not Agree", callback_data="consent_reject")],
        ]

    def _validate_name(self, name: str) -> bool:
        """Validate name input."""
        if not name or len(name.strip()) < 1:
            return False
        if len(name) > 100:
            return False
        return True

    def _transform_name(self, name: str) -> str:
        """Transform name input."""
        return name.strip()

    def _get_user_hash(self, update: Update) -> str:
        """Get or create user hash from update."""
        user = update.effective_user
        if not user:
            raise ValueError("No effective user in update")

        telegram_id = str(user.id)
        return hash_telegram_id(telegram_id)

    async def start(
        self,
        update: Update,
        language: str = "en",
        user_hash: str | None = None,
    ) -> None:
        """
        Start onboarding for a new user.

        Args:
            update: Telegram Update
            language: Auto-detected language from Telegram
            user_hash: Pre-computed user hash (PERF-007: skip HMAC)
        """
        if user_hash is None:
            user_hash = self._get_user_hash(update)
        await self._set_state(user_hash, OnboardingStates.LANGUAGE)

        # Store language (auto-detected or user-selected)
        await self._set_data(user_hash, {
            "language": language if language in CONSENT_TEXTS else DEFAULT_LANGUAGE,
            "name": None,
            "segment": None,
            "consented": False,
        })

        await self._send_prompt(update, user_hash)

    async def get_state(self, user_hash: str) -> OnboardingStates | None:
        """
        Get the current onboarding state for a user.

        Args:
            user_hash: Hashed Telegram ID

        Returns:
            Current onboarding state, or None if not in onboarding
        """
        return await self._get_state(user_hash)

    async def process_step(self, update: Update) -> None:
        """
        Process the current onboarding step.

        Args:
            update: Telegram Update with user response
        """
        user_hash = self._get_user_hash(update)
        current_state = await self._get_state(user_hash)

        if current_state is None:
            # Not in onboarding, ignore
            return

        if current_state == OnboardingStates.COMPLETED:
            return

        # Find current step
        current_step = None
        for step in self._steps:
            if step.state == current_state:
                current_step = step
                break

        if current_step is None:
            logger.error(f"No step found for state: {current_state}")
            return

        # Process based on step type
        if update.callback_query:
            # Keyboard button was pressed
            await self._handle_callback(update, user_hash, current_step)
        elif update.message and update.message.text:
            # Text was entered
            await self._handle_text(update, user_hash, current_step)

    async def _handle_callback(
        self,
        update: Update,
        user_hash: str,
        step: OnboardingStep,
    ) -> None:
        """Handle callback query from inline keyboard."""
        if not update.callback_query or not update.callback_query.data:
            return
        callback_data = update.callback_query.data
        user_data = await self._get_data(user_hash)

        # Reject any callback not in the exact allowlist (prevents injection).
        if callback_data not in ALLOWED_CALLBACKS:
            logger.warning(
                "Rejected invalid callback data: %s for state %s",
                callback_data[:50],
                step.state,
            )
            await update.callback_query.answer()
            return

        # Use exact string matching with a lookup dict instead of startswith().
        LANG_MAP: dict[str, str] = {
            "lang_en": "en", "lang_de": "de", "lang_sr": "sr", "lang_el": "el",
        }
        SEGMENT_MAP: dict[str, str] = {
            "segment_AD": "AD", "segment_AU": "AU", "segment_AH": "AH",
            "segment_NT": "NT", "segment_CU": "CU",
        }

        if step.state == OnboardingStates.LANGUAGE:
            # Language selection - exact match lookup
            if callback_data in LANG_MAP:
                user_data["language"] = LANG_MAP[callback_data]
                await self._set_data(user_hash, user_data)
                await self._advance_state(update, user_hash)

        elif step.state == OnboardingStates.WORKING_STYLE:
            # Segment selection - exact match lookup
            if callback_data in SEGMENT_MAP:
                user_data["segment"] = SEGMENT_MAP[callback_data]
                await self._set_data(user_hash, user_data)
                await self._advance_state(update, user_hash)

        elif step.state == OnboardingStates.CONSENT:
            # Consent response - exact match only
            if callback_data == "consent_accept":
                user_data["consented"] = True
                await self._set_data(user_hash, user_data)
                await self._advance_state(update, user_hash)
            elif callback_data == "consent_reject":
                if update.callback_query.message and hasattr(update.callback_query.message, "edit_text"):
                    await update.callback_query.message.edit_text(
                        "Consent is required to use Aurora Sun. "
                        "You can restart anytime with /start"
                    )
                await self._set_state(user_hash, OnboardingStates.COMPLETED)

        # Answer callback to remove loading state
        await update.callback_query.answer()

    async def _handle_text(
        self,
        update: Update,
        user_hash: str,
        step: OnboardingStep,
    ) -> None:
        """Handle text input from user."""
        if not update.message or not update.message.text:
            return
        text = update.message.text
        user_data = await self._get_data(user_hash)

        if step.state == OnboardingStates.NAME:
            # Name input
            if step.validator and not step.validator(text):
                await update.message.reply_text(
                    "Please enter a valid name (1-100 characters)."
                )
                return

            if step.transformer:
                text = step.transformer(text)

            user_data["name"] = text
            await self._set_data(user_hash, user_data)
            await self._advance_state(update, user_hash)

    async def _advance_state(self, update: Update, user_hash: str) -> None:
        """Advance to the next onboarding state."""
        current_state = await self._get_state(user_hash)

        # Find next step
        next_state = None
        for i, step in enumerate(self._steps):
            if step.state == current_state:
                if i + 1 < len(self._steps):
                    next_state = self._steps[i + 1].state
                else:
                    next_state = OnboardingStates.COMPLETED
                break

        if next_state:
            # Validate the state transition is allowed (state machine integrity).
            if current_state is not None:
                allowed_next = VALID_TRANSITIONS.get(current_state, set())
                if next_state not in allowed_next:
                    logger.error(
                        "Invalid state transition rejected: %s -> %s",
                        current_state,
                        next_state,
                    )
                    return

            await self._set_state(user_hash, next_state)
            await self._send_prompt(update, user_hash)

    async def _send_prompt(self, update: Update, user_hash: str) -> None:
        """Send the prompt for the current state."""
        current_state = await self._get_state(user_hash)
        user_data = await self._get_data(user_hash)
        language = user_data.get("language", DEFAULT_LANGUAGE)

        # Find current step
        current_step = None
        for step in self._steps:
            if step.state == current_state:
                current_step = step
                break

        if current_step is None:
            return

        # Get prompt text based on step
        if current_step.state == OnboardingStates.LANGUAGE:
            text = "Welcome to Aurora Sun! Please select your language:"

        elif current_step.state == OnboardingStates.NAME:
            text = "Great! What's your name?"

        elif current_step.state == OnboardingStates.WORKING_STYLE:
            text = """
How would you describe your brain's operating style?

This helps me adapt the coaching to how you actually work best.

- **ADHD**: I work in bursts, need novelty, get distracted easily
- **Autism**: I need routine, predictability, hate unexpected changes
- **AuDHD**: It's complicated - sometimes one, sometimes the other
- **Neurotypical**: Standard productivity works for me
- **Custom**: I want to configure my own experience
"""

        elif current_step.state == OnboardingStates.CONSENT:
            consent_text = CONSENT_TEXTS.get(language, CONSENT_TEXTS[DEFAULT_LANGUAGE])
            text = f"""
{consent_text}

Please review and accept to continue:
"""

        elif current_step.state == OnboardingStates.CONFIRMATION:
            name = user_data.get("name", "there")
            segment = user_data.get("segment", "Neurotypical")
            segment_display = SEGMENT_DISPLAY_NAMES.get(segment, "Neurotypical")

            text = f"""
You're all set, {name}!

Your profile:
- Segment: {segment_display}
- Language: {language.upper()}

Your daily workflow will adapt to how your brain works.
You can change these settings anytime with /settings.

Type anything to start your first daily planning session!
"""
            await self._set_state(user_hash, OnboardingStates.COMPLETED)

        else:
            text = "Processing..."

        # Send message with keyboard if applicable
        keyboard: list[list[InlineKeyboardButton]] | None = None
        if current_step.keyboard is not None:
            keyboard = current_step.keyboard(language)

        if keyboard is not None:
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(text, reply_markup=reply_markup)
            elif update.callback_query and update.callback_query.message and hasattr(update.callback_query.message, "edit_text"):
                await update.callback_query.message.edit_text(
                    text, reply_markup=reply_markup
                )
        else:
            if update.message:
                await update.message.reply_text(text)
            elif update.callback_query and update.callback_query.message and hasattr(update.callback_query.message, "edit_text"):
                await update.callback_query.message.edit_text(text)

    async def get_user_data(self, user_hash: str) -> dict[str, Any] | None:
        """
        Get collected user data after onboarding.

        Args:
            user_hash: Hashed Telegram ID

        Returns:
            Dictionary with collected data (language, name, segment, consented)
        """
        data = await self._get_data(user_hash)
        return data if data else None


# =============================================================================
# Export
# =============================================================================


__all__ = [
    "OnboardingStates",
    "OnboardingFlow",
    "SEGMENT_DISPLAY_NAMES",
    "CONSENT_TEXTS",
]
