"""
Telegram Webhook Handler for Aurora Sun V1.

This module handles incoming updates from Telegram and routes them through
the Natural Language Interface (NLI) pipeline.

Flow:
    1. Receive Update from Telegram
    2. Extract message/user info
    3. Check consent gate (GDPR)
    4. Pass to NLI (Intent Router)
    5. Route to appropriate module
    6. Return response

References:
    - ARCHITECTURE.md Section 4 (Natural Language Interface)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
    - ARCHITECTURE.md Section 13 (SW-13, SW-15)
"""

import os
import logging
from typing import Optional, Any

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from src.bot.onboarding import OnboardingFlow, OnboardingStates
from src.lib.encryption import hash_telegram_id

logger = logging.getLogger(__name__)


class TelegramWebhookHandler:
    """
    Handles Telegram webhook updates and routes them through the NLI.

    This is the entry point for all Telegram interactions. It handles:
    - New user detection and onboarding trigger
    - Consent gate validation
    - Message routing through Intent Router
    - Response formatting and delivery
    """

    def __init__(
        self,
        nli_service: Any = None,
        db_session: Any = None,
    ):
        """
        Initialize the webhook handler.

        Args:
            nli_service: NLI service for intent routing (optional, lazy loaded)
            db_session: Database session for user lookups (optional, lazy loaded)
        """
        self._nli_service = nli_service
        self._db_session = db_session
        self._onboarding_flow = OnboardingFlow()

    async def handle_update(self, update: Update) -> None:
        """
        Main entry point for handling Telegram updates.

        This is the core handler that:
        1. Extracts message and user info
        2. Validates consent (SW-15)
        3. Routes through NLI
        4. Returns response

        Args:
            update: Telegram Update object
        """
        if not update.message and not update.callback_query:
            logger.warning("Received update without message or callback_query")
            return

        # Extract user info
        user = update.effective_user
        if not user:
            logger.warning("Update has no effective_user")
            return

        telegram_id = str(user.id)
        telegram_id_hash = hash_telegram_id(telegram_id)

        # TODO: Load user from database and check consent
        # For now, route to onboarding for new users
        # user_record = await self._get_user_by_telegram_hash(telegram_id_hash)

        # Handle onboarding state machine
        # if user_record is None:
        #     await self._handle_onboarding(update, user, telegram_id_hash)
        #     return

        # Check consent gate (SW-15)
        # consent_result = await check_consent_gate(self._db_session, user_record.id)
        # if consent_result.status != ConsentStatus.VALID:
        #     await self._request_consent(update, user_record)
        #     return

        # Route through NLI
        await self._route_through_nli(update, user)

    async def _route_through_nli(self, update: Update, user: Any) -> None:
        """
        Route message through the NLI (Intent Router).

        This is where the magic happens:
        1. Extract message text
        2. Pass to Intent Router
        3. Route to appropriate module
        4. Send response

        Args:
            update: Telegram Update
            user: Telegram user object
        """
        # Extract message text
        message_text = update.message.text if update.message else ""
        if not message_text:
            return

        # TODO: Implement actual NLI routing
        # For now, just echo back (scaffold)
        response_text = f"Echo: {message_text}"

        await update.message.reply_text(response_text)

    async def _handle_onboarding(
        self,
        update: Update,
        user: Any,
        telegram_id_hash: str,
    ) -> None:
        """
        Handle new user onboarding flow.

        Implements SW-13: User Onboarding
        1. Language auto-detect via Telegram locale
        2. Welcome message
        3. Segment selection
        4. Consent gate (explicit, not skippable)
        5. Vision capture

        Args:
            update: Telegram Update
            user: Telegram user object
            telegram_id_hash: Hashed Telegram ID
        """
        # Get language from Telegram locale
        language = user.language_code or "en"

        # Get current onboarding state
        state = await self._onboarding_flow.get_state(telegram_id_hash)

        if state is None:
            # Start new onboarding
            await self._onboarding_flow.start(update, language=language)

        # Process current step
        await self._onboarding_flow.process_step(update)

    async def _get_user_by_telegram_hash(self, telegram_id_hash: str) -> Optional[Any]:
        """
        Get user from database by hashed Telegram ID.

        Args:
            telegram_id_hash: HMAC-SHA256 hash of Telegram ID

        Returns:
            User record if found, None otherwise
        """
        # TODO: Implement actual database lookup
        # from src.models.user import User
        # return self._db_session.query(User).filter(
        #     User.telegram_id == telegram_id_hash
        # ).first()
        return None

    async def _request_consent(self, update: Update, user: Any) -> None:
        """
        Request consent from user who hasn't given it yet.

        This is part of the consent gate - no data processing without consent.

        Args:
            update: Telegram Update
            user: User record
        """
        # TODO: Implement consent request flow
        consent_text = (
            "Before we continue, I need your consent to process your data. "
            "Your data is encrypted and stored securely. "
            "You can withdraw consent at any time."
        )
        # Send consent message with inline keyboard


# =============================================================================
# Webhook Setup
# =============================================================================


async def webhook_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main webhook handler for Telegram bot.

    This function is called for every incoming Telegram update.
    It delegates to the TelegramWebhookHandler class.

    Args:
        update: Telegram Update
        context: Telegram context
    """
    handler = TelegramWebhookHandler()
    await handler.handle_update(update)


def create_app() -> Application:
    """
    Create and configure the Telegram Application.

    Returns:
        Configured telegram.ext.Application
    """
    import asyncio

    # Get bot token from environment
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Create application
    application = Application.builder().token(bot_token).build()

    # Add handlers
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            webhook_handler,
        )
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", webhook_handler))
    application.add_handler(CommandHandler("help", webhook_handler))

    return application


# =============================================================================
# Convenience Functions
# =============================================================================


async def process_telegram_update(update: Update) -> str:
    """
    Process a Telegram update and return the response text.

    This is a convenience function for testing and external callers.

    Args:
        update: Telegram Update object

    Returns:
        Response text to send back to user
    """
    handler = TelegramWebhookHandler()
    await handler.handle_update(update)
    return "OK"


__all__ = [
    "TelegramWebhookHandler",
    "webhook_handler",
    "create_app",
    "process_telegram_update",
]
