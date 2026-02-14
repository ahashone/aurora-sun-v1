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

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from src.lib.encryption import hash_telegram_id

logger = logging.getLogger(__name__)


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
- Encrypted end-to-end
- Never shared with third parties
- Stored in EU/Germany
- deletable at any time

You can withdraw consent anytime by typing "/delete".
""",
    "de": """
Ich stimme der Verarbeitung meiner personenbezogenen Daten zum Zweck des KI-Coachings zu.

Verarbeitete Daten:
- Meine Nachrichten und Reflexionen
- Meine Ziele und Aufgaben
- Meine Energie und Stimmung (falls geteilt)

Ihre Daten sind:
- Ende-zu-Ende verschlusselt
- Niemals an Dritte weitergegeben
- In der EU/Deutschland gespeichert
- Jederzeit loschbar

Sie konnen die Einwilligung jederzeit widerrufen mit "/delete".
""",
    "sr": """
Saglasan sam sa obradom mojih licnih podataka u svrhu AI coachiranja.

Obradjeni podaci:
- Moje poruke i refleksije
- Moji ciljevi i zadaci
- Moja energija i raspolozenje (ako podelim)

Vasi podaci su:
- Sifrovani od kraja do kraja
- Nikada ne dele sa trecim licima
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
- Κρυπτογραφημένα από άκρο σε άκρο
- Δεν μοιράζονται ποτέ με τρίτους
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
    keyboard: list[list[InlineKeyboardButton]] | None = None
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

    def __init__(self):
        """Initialize the onboarding flow."""
        self._states: dict[str, OnboardingStates] = {}  # user_hash -> state
        self._user_data: dict[str, dict[str, Any]] = {}  # user_hash -> data

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

    async def start(self, update: Update, language: str = "en") -> None:
        """
        Start onboarding for a new user.

        Args:
            update: Telegram Update
            language: Auto-detected language from Telegram
        """
        user_hash = self._get_user_hash(update)
        self._states[user_hash] = OnboardingStates.LANGUAGE

        # Store language (auto-detected or user-selected)
        self._user_data[user_hash] = {
            "language": language if language in CONSENT_TEXTS else DEFAULT_LANGUAGE,
            "name": None,
            "segment": None,
            "consented": False,
        }

        await self._send_prompt(update, user_hash)

    async def get_state(self, user_hash: str) -> OnboardingStates | None:
        """
        Get the current onboarding state for a user.

        Args:
            user_hash: Hashed Telegram ID

        Returns:
            Current onboarding state, or None if not in onboarding
        """
        return self._states.get(user_hash)

    async def process_step(self, update: Update) -> None:
        """
        Process the current onboarding step.

        Args:
            update: Telegram Update with user response
        """
        user_hash = self._get_user_hash(update)
        current_state = self._states.get(user_hash)

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
        callback_data = update.callback_query.data
        user_data = self._user_data.get(user_hash, {})

        # F-009: Strict allowlists for callback validation
        VALID_LANGUAGES = {"en", "de", "sr", "el"}
        VALID_SEGMENTS = {"AD", "AU", "AH", "NT", "CU"}

        if step.state == OnboardingStates.LANGUAGE:
            # Language selection - strict validation
            if callback_data.startswith("lang_"):
                language = callback_data.replace("lang_", "")
                if language in VALID_LANGUAGES:
                    user_data["language"] = language
                    self._user_data[user_hash] = user_data
                    await self._advance_state(update, user_hash)

        elif step.state == OnboardingStates.WORKING_STYLE:
            # Segment selection - strict validation
            if callback_data.startswith("segment_"):
                segment = callback_data.replace("segment_", "")
                if segment in VALID_SEGMENTS:
                    user_data["segment"] = segment
                    self._user_data[user_hash] = user_data
                    await self._advance_state(update, user_hash)

        elif step.state == OnboardingStates.CONSENT:
            # Consent response - exact match only
            if callback_data == "consent_accept":
                user_data["consented"] = True
                self._user_data[user_hash] = user_data
                await self._advance_state(update, user_hash)
            elif callback_data == "consent_reject":
                await update.callback_query.message.edit_text(
                    "Consent is required to use Aurora Sun. "
                    "You can restart anytime with /start"
                )
                self._states[user_hash] = OnboardingStates.COMPLETED

        # Answer callback to remove loading state
        await update.callback_query.answer()

    async def _handle_text(
        self,
        update: Update,
        user_hash: str,
        step: OnboardingStep,
    ) -> None:
        """Handle text input from user."""
        text = update.message.text
        user_data = self._user_data.get(user_hash, {})

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
            self._user_data[user_hash] = user_data
            await self._advance_state(update, user_hash)

    async def _advance_state(self, update: Update, user_hash: str) -> None:
        """Advance to the next onboarding state."""
        current_state = self._states.get(user_hash)

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
            self._states[user_hash] = next_state
            await self._send_prompt(update, user_hash)

    async def _send_prompt(self, update: Update, user_hash: str) -> None:
        """Send the prompt for the current state."""
        current_state = self._states.get(user_hash)
        user_data = self._user_data.get(user_hash, {})
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
            self._states[user_hash] = OnboardingStates.COMPLETED

        else:
            text = "Processing..."

        # Send message with keyboard if applicable
        keyboard = None
        if current_step.keyboard:
            keyboard = current_step.keyboard(language)

        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.message:
                await update.message.reply_text(text, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.message.edit_text(
                    text, reply_markup=reply_markup
                )
        else:
            if update.message:
                await update.message.reply_text(text)
            elif update.callback_query:
                await update.callback_query.message.edit_text(text)

    def get_user_data(self, user_hash: str) -> dict[str, Any] | None:
        """
        Get collected user data after onboarding.

        Args:
            user_hash: Hashed Telegram ID

        Returns:
            Dictionary with collected data (language, name, segment, consented)
        """
        return self._user_data.get(user_hash)


# =============================================================================
# Export
# =============================================================================


__all__ = [
    "OnboardingStates",
    "OnboardingFlow",
    "SEGMENT_DISPLAY_NAMES",
    "CONSENT_TEXTS",
]
