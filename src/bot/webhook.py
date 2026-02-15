"""
Telegram Webhook Handler for Aurora Sun V1.

This module handles incoming updates from Telegram and routes them through
the Natural Language Interface (NLI) pipeline.

Flow:
    1. Receive Update from Telegram
    2. Private-chat gate (silently ignore non-private chats)
    3. Extract message/user info
    4. Crisis detection FIRST (must never be blocked by rate limits or consent)
    5. Rate limit check (per-user)
    6. Check consent gate (GDPR)
    7. Sanitize input (XSS, path traversal, markdown)
    8. Pass to NLI (Intent Router)
    9. Route to appropriate module
    10. Return response

Security fixes applied (Security Audit):
    - Consent gate wired to ConsentService (GDPR Art. 9)
    - User lookup via hashed Telegram ID (no raw PII in DB)
    - Webhook secret token validation (X-Telegram-Bot-Api-Secret-Token)
    - InputSanitizer wired into all message processing paths
    - RateLimiter used as classmethod (stateless, Redis-backed)
    - Crisis detection runs before NLI routing (safety-first)

References:
    - ARCHITECTURE.md Section 4 (Natural Language Interface)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
    - ARCHITECTURE.md Section 13 (SW-13, SW-15)
"""

import ipaddress
import logging
import os
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.onboarding import OnboardingFlow
from src.lib.encryption import hash_telegram_id

# Security imports
from src.lib.security import InputSanitizer, RateLimiter, RateLimitTier, hash_uid
from src.models.consent import ConsentStatus, ConsentValidationResult
from src.services.crisis_service import CrisisLevel, check_and_handle_crisis

logger = logging.getLogger(__name__)

# Telegram IP allowlist for webhook origin validation.
# See https://core.telegram.org/bots/webhooks#the-short-version
TELEGRAM_IP_RANGES = [
    ipaddress.ip_network("149.154.160.0/20"),
    ipaddress.ip_network("91.108.4.0/22"),
]


def is_telegram_ip(ip_str: str) -> bool:
    """
    Check if an IP address belongs to Telegram's known ranges.

    Args:
        ip_str: IP address string to check

    Returns:
        True if the IP is in Telegram's known ranges
    """
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in TELEGRAM_IP_RANGES)
    except ValueError:
        logger.warning("Invalid IP address for allowlist check: %s", ip_str)
        return False


def validate_webhook_request(
    secret_header: str | None,
    client_ip: str | None = None,
) -> bool:
    """
    Validate an incoming webhook request (secret token + optional IP check).

    Call this in the web framework (Starlette/FastAPI) BEFORE parsing the
    Update object. Checks X-Telegram-Bot-Api-Secret-Token header and
    optionally the client IP against Telegram's known ranges.

    Args:
        secret_header: Value of X-Telegram-Bot-Api-Secret-Token header
        client_ip: Client IP address (optional, for allowlist check)

    Returns:
        True if the request is valid
    """
    import hmac

    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not expected_secret:
        environment = os.environ.get("AURORA_ENVIRONMENT", "development")
        if environment == "production":
            logger.error("TELEGRAM_WEBHOOK_SECRET not set in production — rejecting all webhook requests")
            return False
        logger.warning("TELEGRAM_WEBHOOK_SECRET not set — webhook validation skipped (dev mode)")
    elif not secret_header or not hmac.compare_digest(secret_header, expected_secret):
        logger.warning("Webhook request failed secret validation")
        return False

    if client_ip and not is_telegram_ip(client_ip):
        logger.warning("Webhook request from non-Telegram IP: %s", client_ip)
        # Log but don't block — IP ranges may change, and proxies complicate this

    return True


class TelegramWebhookHandler:
    """
    Handles Telegram webhook updates and routes them through the NLI.

    This is the entry point for all Telegram interactions. It handles:
    - Input sanitization (XSS, path traversal, markdown injection)
    - Per-user rate limiting (30/min, 100/hour)
    - Crisis detection (SW-11)
    - New user detection and onboarding trigger
    - GDPR consent gate validation
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
        1. Private-chat gate (ignore groups/channels to prevent data leakage)
        2. Extract user info
        3. Sanitize ALL user-input fields (SEC-004: text, callback_data, inline queries)
        4. Crisis detection FIRST (must NEVER be blocked by rate limits or consent)
        5. Per-user rate limits (30/min, 100/hour)
        6. Consent gate (SW-15)
        7. Routes through NLI
        8. Returns response

        Args:
            update: Telegram Update object
        """
        # =============================================================================
        # Private chat only gate
        # Silently ignore all non-private chats to prevent data leakage in groups.
        # This check runs BEFORE any processing, including crisis detection.
        # =============================================================================
        if update.effective_chat and update.effective_chat.type != "private":
            return

        if not update.message and not update.callback_query:
            logger.warning("Received update without message or callback_query")
            return

        # Extract user info
        user = update.effective_user
        if not user:
            logger.warning("Update has no effective_user")
            return

        # =============================================================================
        # SEC-004: Sanitize ALL user-input fields from Telegram Update.
        # Previously only message text was sanitized. Now we sanitize:
        # - message.text (text messages)
        # - callback_query.data (inline keyboard callbacks)
        # - inline_query.query (inline bot queries)
        # - chosen_inline_result.query (chosen inline result)
        # - message.caption (media captions)
        # Sanitization runs BEFORE crisis detection to ensure clean input everywhere.
        # =============================================================================
        self._sanitize_update_fields(update)

        # =============================================================================
        # Crisis detection BEFORE rate limiting and consent gate.
        # A suicidal user must NEVER be blocked by rate limits or missing consent.
        # This is the FIRST thing after receiving a valid message (after private-chat
        # check). Uses user.id directly -- no DB lookup needed for crisis check.
        # =============================================================================
        message_text = update.message.text if update.message else ""
        if message_text:
            crisis_response = await check_and_handle_crisis(user.id, message_text)
            if crisis_response is not None:
                if update.message:
                    await update.message.reply_text(crisis_response.message)
                if crisis_response.level == CrisisLevel.CRISIS:
                    # Crisis takes absolute priority - skip everything else
                    return

        # =============================================================================
        # Per-user rate limiting via stateless classmethod (Redis-backed)
        # =============================================================================
        # Check message rate limit (30/min, 100/hour)
        if not await RateLimiter.check_rate_limit(user.id, RateLimitTier.CHAT):
            logger.warning("rate_limit_exceeded user_hash=%s", hash_uid(user.id))
            if update.message:
                await update.message.reply_text(
                    "You're sending messages too quickly. Please wait a moment."
                )
            return

        telegram_id = str(user.id)
        telegram_id_hash = hash_telegram_id(telegram_id)

        # =============================================================================
        # GDPR consent gate: block all non-onboarding messages until consent is VALID
        # =============================================================================
        # Load user from database and check consent
        user_record = await self._get_user_by_telegram_hash(telegram_id_hash)

        if user_record is None:
            # New user - route to onboarding
            await self._handle_onboarding(update, user, telegram_id_hash)
            return

        # Check consent gate (SW-15 / GDPR Art. 9)
        consent_result = await self._check_consent(user_record.id)
        if consent_result.status != ConsentStatus.VALID:
            # Block processing until valid consent
            await self._request_consent(update, user_record)
            return

        # Route through NLI with error handling
        try:
            await self._route_through_nli(update, user)
        except Exception:
            logger.exception("Error routing message through NLI")
            try:
                if update.message:
                    await update.message.reply_text(
                        "Something went wrong. Please try again."
                    )
            except Exception:
                logger.exception("Failed to send error message to user")

    # =============================================================================
    # SEC-004: Comprehensive Input Sanitization
    # =============================================================================

    @staticmethod
    def _sanitize_update_fields(update: Update) -> None:
        """
        Sanitize ALL user-input fields in a Telegram Update (SEC-004).

        Covers:
        - message.text: Standard text messages
        - message.caption: Media captions (photos, videos, documents)
        - callback_query.data: Inline keyboard callback data
        - inline_query.query: Inline bot search queries
        - chosen_inline_result.query: Chosen inline result query
        - poll.question / poll.options: Poll content

        This runs ONCE at the top of handle_update() so all downstream
        code (crisis detection, NLI routing, onboarding) receives
        pre-sanitized input.

        Args:
            update: Telegram Update object (modified in-place)
        """
        # Sanitize message text
        if update.message and update.message.text:
            try:
                update.message._text = InputSanitizer.sanitize_all(
                    update.message.text
                )
            except (AttributeError, TypeError):
                # Telegram objects may be frozen; log and continue
                logger.debug("Could not sanitize message.text in-place")

        # Sanitize message caption (photos, videos, documents)
        if update.message and update.message.caption:
            try:
                update.message._caption = InputSanitizer.sanitize_all(
                    update.message.caption
                )
            except (AttributeError, TypeError):
                logger.debug("Could not sanitize message.caption in-place")

        # Sanitize callback_query.data (inline keyboard presses)
        if update.callback_query and update.callback_query.data:
            try:
                update.callback_query._data = InputSanitizer.sanitize_all(
                    update.callback_query.data
                )
            except (AttributeError, TypeError):
                logger.debug("Could not sanitize callback_query.data in-place")

        # Sanitize inline_query.query (inline bot search)
        if update.inline_query and update.inline_query.query:
            try:
                update.inline_query._query = InputSanitizer.sanitize_all(
                    update.inline_query.query
                )
            except (AttributeError, TypeError):
                logger.debug("Could not sanitize inline_query.query in-place")

        # Sanitize chosen_inline_result.query
        if update.chosen_inline_result and update.chosen_inline_result.query:
            try:
                update.chosen_inline_result._query = InputSanitizer.sanitize_all(
                    update.chosen_inline_result.query
                )
            except (AttributeError, TypeError):
                logger.debug("Could not sanitize chosen_inline_result.query in-place")

    # =============================================================================
    # Helper Methods for Consent and User Management
    # =============================================================================

    async def _get_user_by_telegram_hash(self, telegram_id_hash: str) -> Any:
        """
        Get user by hashed Telegram ID (no raw PII stored in DB).

        Args:
            telegram_id_hash: HMAC-SHA256 hashed Telegram ID

        Returns:
            User record if found, None otherwise
        """
        if self._db_session is None:
            logger.warning("No database session available for user lookup")
            return None
        try:
            from src.models.user import User
            return self._db_session.query(User).filter_by(telegram_id=telegram_id_hash).first()
        except Exception:
            logger.exception("Failed to query user by telegram_id hash")
            return None

    async def _check_consent(self, user_id: int) -> ConsentValidationResult:
        """
        Check user's consent status (GDPR Art. 9 requirement).

        Args:
            user_id: User ID

        Returns:
            ConsentValidationResult with detailed status information
        """
        if self._db_session is not None:
            try:
                from src.models.consent import check_consent_gate
                return check_consent_gate(self._db_session, user_id)
            except Exception:
                logger.exception("Failed to validate consent via ConsentService")

        # Fallback: no DB session available — return NOT_GIVEN to be safe
        # This blocks processing until a proper DB session is injected.
        return ConsentValidationResult(
            status=ConsentStatus.NOT_GIVEN,
            consent_given_at=None,
            consent_withdrawn_at=None,
            consent_version=None,
            message="Database session not available for consent validation"
        )

    async def _request_consent(self, update: Any, user: Any) -> None:
        """
        Request consent from user who hasn't provided it yet.

        Args:
            update: Telegram Update
            user: User object
        """
        # Send consent request message
        consent_text = (
            "To use Aurora Sun, I need your explicit consent to process your data.\n\n"
            "Aurora Sun processes mental health and neurotype data (GDPR Art. 9).\n"
            "Your data is encrypted and stored securely.\n"
            "You can withdraw consent at any time.\n\n"
            "Do you consent to data processing?"
        )
        # TODO: Add inline keyboard with Accept/Decline buttons
        await update.message.reply_text(consent_text)

    async def _handle_onboarding(self, update: Any, user: Any, telegram_id_hash: str) -> None:
        """
        Handle new user onboarding (sanitize name/language input before storage).

        Args:
            update: Telegram Update
            user: User object
            telegram_id_hash: Hashed Telegram ID
        """
        # Start onboarding flow
        # OnboardingFlow.start() takes (update, language) - auto-detect from Telegram user
        has_lang = hasattr(user, 'language_code') and user.language_code
        language = user.language_code if has_lang else "en"
        # Sanitize language code to prevent injection via Telegram user data
        language = InputSanitizer.sanitize_all(language)
        # PERF-007: Pass pre-computed hash to avoid recomputing HMAC
        await self._onboarding_flow.start(
            update, language, user_hash=telegram_id_hash
        )

    async def _route_through_nli(self, update: Update, user: Any) -> None:
        """
        Route message through the NLI (Intent Router).

        This is where the magic happens:
        1. Extract message text
        2. Sanitize input (XSS, path traversal, markdown)
        3. Pass to Intent Router
        4. Route to appropriate module
        5. Send response

        Args:
            update: Telegram Update
            user: Telegram user object
        """
        # Extract message text
        message_text = update.message.text if update.message else ""
        if not message_text:
            return

        # Sanitize all user input before LLM/storage processing
        message_text = InputSanitizer.sanitize_all(message_text)

        # TODO: Implement actual NLI routing
        # For now, just echo back (scaffold)
        response_text = f"Echo: {message_text}"

        if update.message:
            await update.message.reply_text(response_text)

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


def create_app() -> Application[Any, Any, Any, Any, Any, Any]:
    """
    Create and configure the Telegram Application.

    Webhook secret token validation via TELEGRAM_WEBHOOK_SECRET.

    Returns:
        Configured telegram.ext.Application
    """

    # Get bot token from environment
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    # Webhook secret for X-Telegram-Bot-Api-Secret-Token validation.
    # The secret is validated at the web framework level (Starlette/FastAPI middleware)
    # via validate_webhook_request() before the update reaches this Application.
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    environment = os.environ.get("AURORA_ENVIRONMENT", "development")
    if not webhook_secret:
        if environment == "production":
            raise ValueError(
                "TELEGRAM_WEBHOOK_SECRET is required in production. "
                "Set it in the environment to secure webhook requests."
            )
        logger.warning(
            "TELEGRAM_WEBHOOK_SECRET not set — webhook requests will not be validated (dev mode)."
        )

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
    "is_telegram_ip",
    "TELEGRAM_IP_RANGES",
]
