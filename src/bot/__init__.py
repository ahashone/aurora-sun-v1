"""
Bot package for Aurora Sun V1.

This package contains the Telegram bot components:
- webhook.py: Main webhook handler for Telegram updates
- onboarding.py: User onboarding state machine (SW-13)

Usage:
    from src.bot import webhook, onboarding
"""

from src.bot.webhook import (
    TelegramWebhookHandler,
    webhook_handler,
    create_app,
    process_telegram_update,
)
from src.bot.onboarding import (
    OnboardingStates,
    OnboardingFlow,
    SEGMENT_DISPLAY_NAMES,
    CONSENT_TEXTS,
)

__all__ = [
    # Webhook
    "TelegramWebhookHandler",
    "webhook_handler",
    "create_app",
    "process_telegram_update",
    # Onboarding
    "OnboardingStates",
    "OnboardingFlow",
    "SEGMENT_DISPLAY_NAMES",
    "CONSENT_TEXTS",
]
