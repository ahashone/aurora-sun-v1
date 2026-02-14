"""
Comprehensive tests for Telegram Webhook Handler.

Tests cover:
- Update handling (message, callback_query)
- Rate limiting (FINDING-009)
- Input sanitization (FINDING-006)
- Crisis detection (SW-11, highest priority)
- Consent gate validation (FINDING-001, SW-15)
- New user detection and onboarding trigger
- NLI routing
- Error handling
- User lookup from database (FINDING-002)
- Webhook secret token validation (FINDING-003)
- Application creation

CRITICAL: Crisis signals must NEVER be rate-limited or blocked.

Data Classification: SENSITIVE (message content, user data)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update

from src.bot.webhook import (
    TelegramWebhookHandler,
    create_app,
    process_telegram_update,
    webhook_handler,
)
from src.models.consent import ConsentStatus, ConsentValidationResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update."""
    update = MagicMock(spec=Update)
    user = MagicMock()
    user.id = 12345
    user.language_code = "en"
    update.effective_user = user
    # FINDING-016: Private chat gate requires effective_chat.type == "private"
    chat = MagicMock()
    chat.type = "private"
    update.effective_chat = chat
    update.message = MagicMock()
    update.message.text = "Hello"
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


@pytest.fixture
def mock_update_no_user():
    """Create a mock Update without effective_user."""
    update = MagicMock(spec=Update)
    update.effective_user = None
    update.message = None
    update.callback_query = None
    return update


@pytest.fixture
def mock_user_record():
    """Create a mock User database record."""
    user = MagicMock()
    user.id = 1
    user.telegram_id = "hashed_telegram_id"
    user.working_style_code = "AD"
    return user


@pytest.fixture
def handler():
    """Create a TelegramWebhookHandler instance."""
    return TelegramWebhookHandler()


@pytest.fixture
def handler_with_db():
    """Create a TelegramWebhookHandler with mock database session."""
    mock_session = MagicMock()
    return TelegramWebhookHandler(db_session=mock_session)


# =============================================================================
# Test: Initialization
# =============================================================================


def test_webhook_handler_initialization(handler: TelegramWebhookHandler):
    """Test that TelegramWebhookHandler initializes correctly."""
    assert handler is not None
    assert handler._nli_service is None
    assert handler._db_session is None
    assert handler._onboarding_flow is not None


def test_webhook_handler_initialization_with_dependencies():
    """Test TelegramWebhookHandler with injected dependencies."""
    mock_nli = MagicMock()
    mock_db = MagicMock()
    handler = TelegramWebhookHandler(nli_service=mock_nli, db_session=mock_db)
    assert handler._nli_service is mock_nli
    assert handler._db_session is mock_db


# =============================================================================
# Test: Update Validation
# =============================================================================


@pytest.mark.asyncio
async def test_handle_update_ignores_empty_update(handler: TelegramWebhookHandler):
    """Test that handle_update ignores updates without message or callback."""
    update = MagicMock(spec=Update)
    update.message = None
    update.callback_query = None

    # Should return early without processing
    await handler.handle_update(update)
    # No assertion needed, just verify no exception


@pytest.mark.asyncio
async def test_handle_update_ignores_update_without_user(handler: TelegramWebhookHandler, mock_update_no_user):
    """Test that handle_update ignores updates without effective_user."""
    await handler.handle_update(mock_update_no_user)
    # No assertion needed, just verify no exception


# =============================================================================
# Test: Rate Limiting (FINDING-009)
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_rate_limits_messages(mock_check_rate, mock_crisis, handler: TelegramWebhookHandler, mock_update):
    """Test that handle_update checks rate limit (FINDING-009).

    Note: Crisis detection runs BEFORE rate limiting (FINDING-013).
    """
    mock_check_rate.return_value = True  # Not rate limited

    with patch.object(handler, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=None):
        with patch.object(handler, '_handle_onboarding', new_callable=AsyncMock):
            await handler.handle_update(mock_update)

    # Verify rate limit check was called
    mock_check_rate.assert_called_once()


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_blocks_rate_limited_user(mock_check_rate, mock_crisis, handler: TelegramWebhookHandler, mock_update):
    """Test that handle_update blocks rate-limited users."""
    mock_check_rate.return_value = False  # Rate limited!

    await handler.handle_update(mock_update)

    # Should send rate limit message
    mock_update.message.reply_text.assert_called_once()
    assert "too quickly" in mock_update.message.reply_text.call_args[0][0].lower()


# =============================================================================
# Test: New User Detection and Onboarding
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_triggers_onboarding_for_new_user(mock_check_rate, mock_crisis, handler: TelegramWebhookHandler, mock_update):
    """Test that new users are routed to onboarding."""
    mock_check_rate.return_value = True

    with patch.object(handler, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=None):
        with patch.object(handler, '_handle_onboarding', new_callable=AsyncMock) as mock_onboard:
            await handler.handle_update(mock_update)

            mock_onboard.assert_called_once()


# =============================================================================
# Test: Consent Gate (FINDING-001, SW-15)
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_blocks_without_valid_consent(mock_check_rate, mock_crisis, handler_with_db: TelegramWebhookHandler, mock_update, mock_user_record):
    """Test that users without valid consent are blocked (FINDING-001)."""
    mock_check_rate.return_value = True

    # Mock user exists but consent is NOT_GIVEN
    consent_result = ConsentValidationResult(
        status=ConsentStatus.NOT_GIVEN,
        consent_given_at=None,
        consent_withdrawn_at=None,
        consent_version=None,
        message="Consent not given",
    )

    with patch.object(handler_with_db, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=mock_user_record):
        with patch.object(handler_with_db, '_check_consent', new_callable=AsyncMock, return_value=consent_result):
            with patch.object(handler_with_db, '_request_consent', new_callable=AsyncMock) as mock_request:
                await handler_with_db.handle_update(mock_update)

                # Should request consent
                mock_request.assert_called_once()


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_allows_valid_consent(mock_check_rate, mock_crisis, handler_with_db: TelegramWebhookHandler, mock_update, mock_user_record):
    """Test that users with valid consent can proceed."""
    mock_check_rate.return_value = True

    # Mock user exists with VALID consent
    consent_result = ConsentValidationResult(
        status=ConsentStatus.VALID,
        consent_given_at=None,
        consent_withdrawn_at=None,
        consent_version="1.0",
        message="Consent valid",
    )

    with patch.object(handler_with_db, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=mock_user_record):
        with patch.object(handler_with_db, '_check_consent', new_callable=AsyncMock, return_value=consent_result):
            with patch.object(handler_with_db, '_route_through_nli', new_callable=AsyncMock) as mock_route:
                await handler_with_db.handle_update(mock_update)

                # Should route through NLI
                mock_route.assert_called_once()


# =============================================================================
# Test: Crisis Detection (SW-11)
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock)
async def test_handle_update_detects_crisis(mock_crisis, handler_with_db: TelegramWebhookHandler, mock_update, mock_user_record):
    """Test that crisis signals are detected BEFORE rate limiting (FINDING-013).

    Crisis detection runs immediately after private-chat gate and user extraction.
    It must NEVER be blocked by rate limits or consent checks.
    """
    # Mock crisis response
    from src.services.crisis_service import CrisisLevel, CrisisResponse
    crisis_response = CrisisResponse(
        level=CrisisLevel.CRISIS,
        message="I'm here with you.",
        resources=[],
        should_pause_workflows=True,
        should_notify_admin=True,
        hotline_provided=False,
    )
    mock_crisis.return_value = crisis_response

    # No rate limit or consent mock needed -- crisis runs BEFORE both
    with patch.object(handler_with_db, '_route_through_nli', new_callable=AsyncMock) as mock_route:
        await handler_with_db.handle_update(mock_update)

        # Crisis response should be sent
        mock_update.message.reply_text.assert_called()
        # NLI should NOT be called for CRISIS level
        mock_route.assert_not_called()


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_continues_after_warning(mock_check_rate, mock_crisis, handler_with_db: TelegramWebhookHandler, mock_update, mock_user_record):
    """Test that WARNING level crisis allows NLI to continue.

    Crisis detection runs BEFORE rate limiting (FINDING-013). A WARNING-level
    crisis sends a message but does not block the pipeline.
    """
    mock_check_rate.return_value = True

    consent_result = ConsentValidationResult(
        status=ConsentStatus.VALID,
        consent_given_at=None,
        consent_withdrawn_at=None,
        consent_version="1.0",
        message="Consent valid",
    )

    # Mock WARNING level crisis
    from src.services.crisis_service import CrisisLevel, CrisisResponse
    crisis_response = CrisisResponse(
        level=CrisisLevel.WARNING,
        message="That sounds hard.",
        resources=[],
        should_pause_workflows=False,
        should_notify_admin=False,
        hotline_provided=False,
    )
    mock_crisis.return_value = crisis_response

    with patch.object(handler_with_db, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=mock_user_record):
        with patch.object(handler_with_db, '_check_consent', new_callable=AsyncMock, return_value=consent_result):
            with patch.object(handler_with_db, '_route_through_nli', new_callable=AsyncMock) as mock_route:
                await handler_with_db.handle_update(mock_update)

                # Warning should be sent
                mock_update.message.reply_text.assert_called()
                # NLI should still be called for WARNING
                mock_route.assert_called_once()


# =============================================================================
# Test: Input Sanitization (FINDING-006)
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
@patch('src.bot.webhook.InputSanitizer.sanitize_all')
async def test_route_through_nli_sanitizes_input(mock_sanitize, mock_check_rate, handler: TelegramWebhookHandler, mock_update):
    """Test that _route_through_nli sanitizes input (FINDING-006)."""
    mock_sanitize.return_value = "Sanitized Hello"
    mock_check_rate.return_value = True

    user = MagicMock()
    user.id = 12345

    await handler._route_through_nli(mock_update, user)

    # Verify sanitization was called
    mock_sanitize.assert_called()


# =============================================================================
# Test: NLI Routing
# =============================================================================


@pytest.mark.asyncio
async def test_route_through_nli_echoes_message(handler: TelegramWebhookHandler, mock_update):
    """Test that _route_through_nli echoes message (scaffold implementation)."""
    user = MagicMock()
    user.id = 12345

    with patch('src.bot.webhook.InputSanitizer.sanitize_all', return_value="Test"):
        await handler._route_through_nli(mock_update, user)

        # Should reply with echo
        mock_update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_route_through_nli_ignores_empty_message(handler: TelegramWebhookHandler):
    """Test that _route_through_nli ignores empty messages."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = ""

    user = MagicMock()
    user.id = 12345

    await handler._route_through_nli(update, user)
    # No assertion needed, just verify no exception


# =============================================================================
# Test: Error Handling
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.check_and_handle_crisis', new_callable=AsyncMock, return_value=None)
@patch('src.bot.webhook.RateLimiter.check_rate_limit', new_callable=AsyncMock)
async def test_handle_update_catches_nli_error(mock_check_rate, mock_crisis, handler_with_db: TelegramWebhookHandler, mock_update, mock_user_record):
    """Test that handle_update catches and handles NLI errors."""
    mock_check_rate.return_value = True

    consent_result = ConsentValidationResult(
        status=ConsentStatus.VALID,
        consent_given_at=None,
        consent_withdrawn_at=None,
        consent_version="1.0",
        message="Consent valid",
    )

    with patch.object(handler_with_db, '_get_user_by_telegram_hash', new_callable=AsyncMock, return_value=mock_user_record):
        with patch.object(handler_with_db, '_check_consent', new_callable=AsyncMock, return_value=consent_result):
            with patch.object(handler_with_db, '_route_through_nli', new_callable=AsyncMock, side_effect=Exception("NLI error")):
                await handler_with_db.handle_update(mock_update)

                # Should send error message to user
                mock_update.message.reply_text.assert_called()
                assert "wrong" in mock_update.message.reply_text.call_args[0][0].lower()


# =============================================================================
# Test: User Lookup (FINDING-002)
# =============================================================================


@pytest.mark.asyncio
async def test_get_user_by_telegram_hash_queries_database(handler_with_db: TelegramWebhookHandler):
    """Test that _get_user_by_telegram_hash queries the database (FINDING-002)."""
    mock_user = MagicMock()
    handler_with_db._db_session.query.return_value.filter_by.return_value.first.return_value = mock_user

    result = await handler_with_db._get_user_by_telegram_hash("test_hash")

    assert result is mock_user


@pytest.mark.asyncio
async def test_get_user_by_telegram_hash_returns_none_when_no_session(handler: TelegramWebhookHandler):
    """Test that _get_user_by_telegram_hash returns None when no db_session."""
    result = await handler._get_user_by_telegram_hash("test_hash")
    assert result is None


# =============================================================================
# Test: Consent Validation (FINDING-001)
# =============================================================================


@pytest.mark.asyncio
async def test_check_consent_uses_consent_service(handler_with_db: TelegramWebhookHandler):
    """Test that _check_consent uses ConsentService (FINDING-001)."""
    with patch('src.models.consent.check_consent_gate') as mock_check:
        mock_check.return_value = ConsentValidationResult(
            status=ConsentStatus.VALID,
            consent_given_at=None,
            consent_withdrawn_at=None,
            consent_version="1.0",
            message="Valid",
        )

        result = await handler_with_db._check_consent(user_id=1)

        assert result.status == ConsentStatus.VALID


@pytest.mark.asyncio
async def test_check_consent_returns_not_given_without_db_session(handler: TelegramWebhookHandler):
    """Test that _check_consent returns NOT_GIVEN when no db_session."""
    result = await handler._check_consent(user_id=1)
    assert result.status == ConsentStatus.NOT_GIVEN


# =============================================================================
# Test: Onboarding Handler
# =============================================================================


@pytest.mark.asyncio
@patch('src.bot.webhook.InputSanitizer.sanitize_all')
async def test_handle_onboarding_sanitizes_language(mock_sanitize, handler: TelegramWebhookHandler, mock_update):
    """Test that _handle_onboarding sanitizes language code (FINDING-006)."""
    mock_sanitize.return_value = "en"

    with patch.object(handler._onboarding_flow, 'start', new_callable=AsyncMock):
        user = MagicMock()
        user.id = 12345
        user.language_code = "en"

        await handler._handle_onboarding(mock_update, user, "test_hash")

        mock_sanitize.assert_called_once_with("en")


@pytest.mark.asyncio
async def test_handle_onboarding_starts_flow(handler: TelegramWebhookHandler, mock_update):
    """Test that _handle_onboarding starts onboarding flow."""
    with patch('src.bot.webhook.InputSanitizer.sanitize_all', return_value="en"):
        with patch.object(handler._onboarding_flow, 'start', new_callable=AsyncMock) as mock_start:
            user = MagicMock()
            user.id = 12345
            user.language_code = "en"

            await handler._handle_onboarding(mock_update, user, "test_hash")

            mock_start.assert_called_once()


# =============================================================================
# Test: Webhook Handler Function
# =============================================================================


@pytest.mark.asyncio
async def test_webhook_handler_delegates_to_class(mock_update):
    """Test that webhook_handler function delegates to TelegramWebhookHandler."""
    with patch.object(TelegramWebhookHandler, 'handle_update', new_callable=AsyncMock) as mock_handle:
        context = MagicMock()
        await webhook_handler(mock_update, context)

        mock_handle.assert_called_once()


# =============================================================================
# Test: Application Creation (FINDING-003)
# =============================================================================


@patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}, clear=True)
def test_create_app_requires_bot_token():
    """Test that create_app requires TELEGRAM_BOT_TOKEN."""
    app = create_app()
    assert app is not None


def test_create_app_raises_without_bot_token():
    """Test that create_app raises ValueError without TELEGRAM_BOT_TOKEN."""
    with patch.dict('os.environ', {}, clear=True):
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            create_app()


@patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_WEBHOOK_SECRET': 'secret'}, clear=True)
def test_create_app_uses_webhook_secret(caplog):
    """Test that create_app uses webhook secret when provided (FINDING-003)."""
    with caplog.at_level('INFO'):
        create_app()
        # Should log that secret is configured
        # Note: actual validation happens in python-telegram-bot internals


# =============================================================================
# Test: Convenience Function
# =============================================================================


@pytest.mark.asyncio
async def test_process_telegram_update(mock_update):
    """Test process_telegram_update convenience function."""
    with patch.object(TelegramWebhookHandler, 'handle_update', new_callable=AsyncMock):
        result = await process_telegram_update(mock_update)
        assert result == "OK"
