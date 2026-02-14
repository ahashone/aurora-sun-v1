"""
Deep Onboarding Module for Aurora Sun V1.

Implements ROADMAP 5.1: Deep Onboarding with Quick Start / Deep Dive paths.

Flow Types:
    - Quick Start: Name → Segment → Consent → Done (3-5 min)
    - Deep Dive: Name → Segment → Energy Pattern → Work Style → Burnout History
                 → Consent → Done (10-15 min)

Features:
    - Conversational (no command lists)
    - User-facing segment names translated per language
    - Auto-language detection via Telegram locale
    - Natural language transitions between steps
    - Segment-aware prompts (different questions for AD/AU/AH)

Reference: ROADMAP 5.1, ARCHITECTURE.md Section 13 (SW-13)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.core.segment_context import WorkingStyleCode
from src.i18n import LanguageCode
from src.lib.i18n import get_i18n_service

logger = logging.getLogger(__name__)


class OnboardingPath(StrEnum):
    """Onboarding path types."""

    QUICK_START = "quick_start"
    DEEP_DIVE = "deep_dive"


class DeepOnboardingState(StrEnum):
    """Deep onboarding state machine states."""

    # Common states
    WELCOME = "welcome"
    PATH_SELECTION = "path_selection"
    LANGUAGE = "language"
    NAME = "name"
    SEGMENT = "segment"
    CONSENT = "consent"
    COMPLETE = "complete"

    # Deep Dive only
    ENERGY_PATTERN = "energy_pattern"
    WORK_STYLE_DETAILS = "work_style_details"
    BURNOUT_HISTORY = "burnout_history"
    SENSORY_PREFERENCES = "sensory_preferences"


@dataclass
class OnboardingData:
    """Data collected during onboarding."""

    # Common fields
    language: LanguageCode = "en"
    name: str = ""
    segment: WorkingStyleCode | None = None
    path: OnboardingPath = OnboardingPath.QUICK_START
    consent_given: bool = False

    # Deep Dive fields
    energy_pattern: str | None = None  # "morning" | "evening" | "variable"
    work_style_details: str | None = None  # Free text
    burnout_history: str | None = None  # "none" | "occasional" | "frequent" | "current"
    sensory_preferences: dict[str, Any] | None = None  # Light, sound, texture preferences


class DeepOnboardingModule:
    """
    Deep onboarding module with Quick Start / Deep Dive paths.

    Provides a conversational onboarding experience that adapts to the user's
    segment and preferred depth.
    """

    def __init__(self) -> None:
        """Initialize the deep onboarding module."""
        self.i18n = get_i18n_service()

    def get_welcome_message(self, lang: LanguageCode) -> str:
        """
        Get the welcome message for the user.

        Args:
            lang: User's language

        Returns:
            Welcome message
        """
        return self.i18n.translate(lang, "onboarding", "welcome_intro")

    def get_path_selection_prompt(self, lang: LanguageCode) -> dict[str, Any]:
        """
        Get the path selection prompt (Quick Start vs Deep Dive).

        Args:
            lang: User's language

        Returns:
            Dict with message and options
        """
        if lang == "en":
            message = (
                "How would you like to get started?\n\n"
                "🚀 **Quick Start** (3-5 min): Get started right away with the essentials.\n"
                "🔍 **Deep Dive** (10-15 min): Help me understand your needs better for a more personalized experience."
            )
            options = [
                {"text": "🚀 Quick Start", "value": OnboardingPath.QUICK_START},
                {"text": "🔍 Deep Dive", "value": OnboardingPath.DEEP_DIVE},
            ]
        elif lang == "de":
            message = (
                "Wie moechtest du beginnen?\n\n"
                "🚀 **Schnellstart** (3-5 Min): Sofort mit den Grundlagen loslegen.\n"
                "🔍 **Ausfuehrlich** (10-15 Min): Hilf mir, deine Beduerfnisse besser zu verstehen fuer eine personalisierte Erfahrung."
            )
            options = [
                {"text": "🚀 Schnellstart", "value": OnboardingPath.QUICK_START},
                {"text": "🔍 Ausfuehrlich", "value": OnboardingPath.DEEP_DIVE},
            ]
        elif lang == "sr":
            message = (
                "Kako želite da počnete?\n\n"
                "🚀 **Brzi start** (3-5 min): Počnite odmah sa osnovama.\n"
                "🔍 **Detaljan uvod** (10-15 min): Pomozite mi da bolje razumem vaše potrebe za personalizovano iskustvo."
            )
            options = [
                {"text": "🚀 Brzi start", "value": OnboardingPath.QUICK_START},
                {"text": "🔍 Detaljan uvod", "value": OnboardingPath.DEEP_DIVE},
            ]
        elif lang == "el":
            message = (
                "Πώς θα θέλατε να ξεκινήσετε;\n\n"
                "🚀 **Γρήγορη Έναρξη** (3-5 λεπτά): Ξεκινήστε αμέσως με τα βασικά.\n"
                "🔍 **Εις Βάθος** (10-15 λεπτά): Βοηθήστε με να κατανοήσω καλύτερα τις ανάγκες σας για μια πιο προσωπική εμπειρία."
            )
            options = [
                {"text": "🚀 Γρήγορη Έναρξη", "value": OnboardingPath.QUICK_START},
                {"text": "🔍 Εις Βάθος", "value": OnboardingPath.DEEP_DIVE},
            ]
        else:
            # Fallback to English
            return self.get_path_selection_prompt("en")

        return {"message": message, "options": options}

    def get_segment_prompt(
        self,
        lang: LanguageCode,
        path: OnboardingPath,
    ) -> dict[str, Any]:
        """
        Get the segment selection prompt.

        The prompt differs based on the path:
        - Quick Start: Simple question with segment options
        - Deep Dive: More detailed explanation with segment characteristics

        Args:
            lang: User's language
            path: Onboarding path

        Returns:
            Dict with message and segment options
        """
        if path == OnboardingPath.QUICK_START:
            message = self.i18n.translate(
                lang, "onboarding", "working_style_title"
            )
        else:
            # Deep Dive: More context
            if lang == "en":
                message = (
                    "To personalize Aurora to your brain, I need to understand how you work best.\n\n"
                    "Choose the description that resonates most with you:"
                )
            elif lang == "de":
                message = (
                    "Um Aurora an dein Gehirn anzupassen, muss ich verstehen, wie du am besten arbeitest.\n\n"
                    "Waehle die Beschreibung, die am besten zu dir passt:"
                )
            elif lang == "sr":
                message = (
                    "Da bih prilagodio Auroru vašem mozgu, moram da razumem kako najbolje radite.\n\n"
                    "Izaberite opis koji vam najviše odgovara:"
                )
            elif lang == "el":
                message = (
                    "Για να προσαρμόσω την Aurora στον εγκέφαλό σας, πρέπει να καταλάβω πώς δουλεύετε καλύτερα.\n\n"
                    "Επιλέξτε την περιγραφή που σας ταιριάζει περισσότερο:"
                )
            else:
                message = self.get_segment_prompt("en", path)["message"]

        # Get translated segment options
        options = []
        for code in ["AD", "AU", "AH", "NT", "CU"]:
            display_name = self.i18n.translate_segment(lang, code)
            description = self.i18n.translate(
                lang, "onboarding", f"working_style_{code}"
            )
            options.append({
                "code": code,
                "display_name": display_name,
                "description": description,
            })

        return {"message": message, "options": options}

    def get_energy_pattern_prompt(
        self,
        lang: LanguageCode,
        segment: WorkingStyleCode,
    ) -> dict[str, Any]:
        """
        Get the energy pattern prompt (Deep Dive only).

        Uses SegmentContext fields (never ``if segment == "AD"``):
        - channel_dominance_enabled: Focus on channel dominance, spoon drawer (AH)
        - routine_anchoring: Focus on routine, sensory impact on energy (AU)
        - icnu_enabled (without channel_dominance): Energy fluctuations, crash patterns (AD)
        - Default: Standard energy patterns (NT/CU)

        Args:
            lang: User's language
            segment: User's segment

        Returns:
            Dict with message and options
        """
        from src.core.segment_context import SegmentContext

        ctx = SegmentContext.from_code(segment)

        if ctx.features.channel_dominance_enabled:
            if lang == "en":
                message = (
                    "AuDHD energy is complex. What's most true for you?\n\n"
                    "(Many AuDHDers have a 'dominant channel' - ADHD or Autism - that drives energy patterns)"
                )
                options = [
                    {"text": "ADHD energy dominates (boom-bust)", "value": "adhd_dominant"},
                    {"text": "Autism energy dominates (sensory-dependent)", "value": "autism_dominant"},
                    {"text": "Both channels active (exhausting!)", "value": "both_active"},
                    {"text": "Varies by day/context", "value": "variable"},
                ]
            else:
                return self.get_energy_pattern_prompt("en", segment)
        elif ctx.features.routine_anchoring:
            if lang == "en":
                message = (
                    "How does your energy relate to your daily routine?\n\n"
                    "(Autistic energy often depends on predictability and sensory environment)"
                )
                options = [
                    {"text": "Best when routine is stable", "value": "routine_stable"},
                    {"text": "Crashes after social/sensory load", "value": "sensory_crash"},
                    {"text": "Consistent through the day", "value": "consistent"},
                    {"text": "Hard to predict", "value": "variable"},
                ]
            else:
                return self.get_energy_pattern_prompt("en", segment)
        elif ctx.features.icnu_enabled:
            if lang == "en":
                message = "When do you typically have the most energy and focus?"
                options = [
                    {"text": "Morning bursts", "value": "morning"},
                    {"text": "Afternoon peaks", "value": "afternoon"},
                    {"text": "Evening energy", "value": "evening"},
                    {"text": "Totally unpredictable", "value": "variable"},
                ]
            else:
                return self.get_energy_pattern_prompt("en", segment)
        else:  # NT, CU (no special features)
            if lang == "en":
                message = "When do you typically have the most energy?"
                options = [
                    {"text": "Morning", "value": "morning"},
                    {"text": "Afternoon", "value": "afternoon"},
                    {"text": "Evening", "value": "evening"},
                    {"text": "Consistent throughout", "value": "consistent"},
                ]
            else:
                return self.get_energy_pattern_prompt("en", segment)

        return {"message": message, "options": options}

    def get_burnout_history_prompt(
        self,
        lang: LanguageCode,
        segment: WorkingStyleCode,
    ) -> dict[str, Any]:
        """
        Get the burnout history prompt (Deep Dive only).

        Uses SegmentContext.neuro.burnout_model (never ``if segment == "AD"``):
        - boom_bust: ADHD boom-bust cycles
        - overload_shutdown: Autistic overload → shutdown
        - three_type: AuDHD all three types (boom-bust, shutdown, double)
        - standard/default: Standard burnout

        Args:
            lang: User's language
            segment: User's segment

        Returns:
            Dict with message and options
        """
        from src.core.segment_context import SegmentContext

        ctx = SegmentContext.from_code(segment)
        burnout_model = ctx.neuro.burnout_model

        if burnout_model == "boom_bust":
            if lang == "en":
                message = (
                    "ADHD burnout often looks like boom-bust cycles.\n\n"
                    "How often do you experience energy crashes after intense periods?"
                )
                options = [
                    {"text": "Never or rarely", "value": "none"},
                    {"text": "Sometimes (monthly)", "value": "occasional"},
                    {"text": "Often (weekly)", "value": "frequent"},
                    {"text": "Currently in a crash", "value": "current"},
                ]
            else:
                return self.get_burnout_history_prompt("en", segment)
        elif burnout_model == "overload_shutdown":
            if lang == "en":
                message = (
                    "Autistic burnout often involves shutdown after prolonged overload.\n\n"
                    "How often do you experience shutdown (loss of skills, need to withdraw)?"
                )
                options = [
                    {"text": "Never or rarely", "value": "none"},
                    {"text": "Sometimes (a few times a year)", "value": "occasional"},
                    {"text": "Often (monthly or more)", "value": "frequent"},
                    {"text": "Currently in shutdown", "value": "current"},
                ]
            else:
                return self.get_burnout_history_prompt("en", segment)
        elif burnout_model == "three_type":
            if lang == "en":
                message = (
                    "AuDHD burnout can be boom-bust, shutdown, or both (double burnout).\n\n"
                    "What's your experience?"
                )
                options = [
                    {"text": "Boom-bust cycles (ADHD-type)", "value": "boom_bust"},
                    {"text": "Shutdown (Autism-type)", "value": "shutdown"},
                    {"text": "Both (double burnout)", "value": "double"},
                    {"text": "Not currently an issue", "value": "none"},
                ]
            else:
                return self.get_burnout_history_prompt("en", segment)
        else:  # standard burnout model (NT, CU)
            if lang == "en":
                message = "Have you experienced burnout in the past?"
                options = [
                    {"text": "Never", "value": "none"},
                    {"text": "Once or twice", "value": "occasional"},
                    {"text": "Multiple times", "value": "frequent"},
                    {"text": "Currently experiencing it", "value": "current"},
                ]
            else:
                return self.get_burnout_history_prompt("en", segment)

        return {"message": message, "options": options}

    def get_completion_message(
        self,
        lang: LanguageCode,
        data: OnboardingData,
    ) -> str:
        """
        Get the completion message after onboarding.

        Personalized based on path and segment.

        Args:
            lang: User's language
            data: Collected onboarding data

        Returns:
            Completion message
        """
        segment_display = self.i18n.translate_segment(
            lang, data.segment or "NT"
        )

        if data.path == OnboardingPath.QUICK_START:
            if lang == "en":
                return (
                    f"Perfect, {data.name}! You're all set.\n\n"
                    f"I'll adapt my coaching to your {segment_display} needs. "
                    "Let's start with your first task."
                )
            elif lang == "de":
                return (
                    f"Perfekt, {data.name}! Du bist bereit.\n\n"
                    f"Ich werde mein Coaching an deine {segment_display}-Beduerfnisse anpassen. "
                    "Lass uns mit deiner ersten Aufgabe beginnen."
                )
            elif lang == "sr":
                return (
                    f"Savršeno, {data.name}! Spremni ste.\n\n"
                    f"Prilagodiću coaching vašim {segment_display} potrebama. "
                    "Hajde da počnemo sa prvim zadatkom."
                )
            elif lang == "el":
                return (
                    f"Τέλεια, {data.name}! Είστε έτοιμοι.\n\n"
                    f"Θα προσαρμόσω το coaching στις ανάγκες σας ως {segment_display}. "
                    "Ας ξεκινήσουμε με την πρώτη εργασία."
                )
        else:  # Deep Dive
            if lang == "en":
                return (
                    f"Thank you for sharing all that, {data.name}! 🙏\n\n"
                    f"I now have a much better understanding of your {segment_display} brain. "
                    "I'll use this to personalize every interaction.\n\n"
                    "Ready to start?"
                )
            elif lang == "de":
                return (
                    f"Danke, dass du das alles geteilt hast, {data.name}! 🙏\n\n"
                    f"Ich verstehe jetzt dein {segment_display}-Gehirn viel besser. "
                    "Ich werde das nutzen, um jede Interaktion zu personalisieren.\n\n"
                    "Bereit zu starten?"
                )
            elif lang == "sr":
                return (
                    f"Hvala što ste podelili sve to, {data.name}! 🙏\n\n"
                    f"Sada mnogo bolje razumem vaš {segment_display} mozak. "
                    "Koristiću ovo da personalizujem svaku interakciju.\n\n"
                    "Spremni za početak?"
                )
            elif lang == "el":
                return (
                    f"Ευχαριστώ που μοιραστήκατε όλα αυτά, {data.name}! 🙏\n\n"
                    f"Τώρα καταλαβαίνω πολύ καλύτερα τον {segment_display} εγκέφαλό σας. "
                    "Θα το χρησιμοποιήσω για να προσαρμόσω κάθε αλληλεπίδραση.\n\n"
                    "Έτοιμοι να ξεκινήσετε;"
                )

        # Fallback
        return self.i18n.translate(
            lang, "onboarding", "onboarding_complete", name=data.name
        )


__all__ = [
    "DeepOnboardingModule",
    "OnboardingPath",
    "DeepOnboardingState",
    "OnboardingData",
]
