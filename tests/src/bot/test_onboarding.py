"""
Comprehensive tests for OnboardingFlow (SW-13: User Onboarding).

Tests cover:
- OnboardingStates enum values
- Language detection and selection
- Name collection and validation
- Working style (segment) selection
- Consent gate (MANDATORY, not skippable - GDPR Art. 9)
- Redis state persistence (with in-memory fallback)
- Keyboard generation (language, segment, consent)
- Input validation (name length, valid segments)
- State transitions
- User data collection
- Callback data validation (FINDING-009: strict allowlists)

CRITICAL: Consent gate is NOT skippable. This is a GDPR compliance requirement.

Data Classification: INTERNAL (onboarding state), SENSITIVE (name, language, segment)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardButton, Update

from src.bot.onboarding import (
    CONSENT_TEXTS,
    DEFAULT_LANGUAGE,
    SEGMENT_CODES,
    SEGMENT_DISPLAY_NAMES,
    OnboardingFlow,
    OnboardingStates,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def onboarding_flow():
    """Create an OnboardingFlow instance."""
    return OnboardingFlow()


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update."""
    update = MagicMock(spec=Update)
    user = MagicMock()
    user.id = 12345
    user.language_code = "en"
    update.effective_user = user
    update.message = None
    update.callback_query = None
    return update


@pytest.fixture
def mock_update_with_message(mock_update):
    """Create a mock Update with a message."""
    message = MagicMock()
    message.text = "Test Name"
    message.reply_text = AsyncMock()
    mock_update.message = message
    return mock_update


@pytest.fixture
def mock_update_with_callback(mock_update):
    """Create a mock Update with a callback query."""
    callback_query = MagicMock()
    callback_query.data = "lang_en"
    callback_query.answer = AsyncMock()
    callback_query.message = MagicMock()
    callback_query.message.edit_text = AsyncMock()
    mock_update.callback_query = callback_query
    return mock_update


# =============================================================================
# Test: OnboardingStates Enum
# =============================================================================


def test_onboarding_states_values():
    """Test that OnboardingStates enum has all expected values."""
    assert OnboardingStates.LANGUAGE == "language"
    assert OnboardingStates.NAME == "name"
    assert OnboardingStates.WORKING_STYLE == "working_style"
    assert OnboardingStates.CONSENT == "consent"
    assert OnboardingStates.CONFIRMATION == "confirmation"
    assert OnboardingStates.COMPLETED == "completed"


# =============================================================================
# Test: Segment Display Names
# =============================================================================


def test_segment_display_names():
    """Test that segment display names map correctly."""
    assert SEGMENT_DISPLAY_NAMES["AD"] == "ADHD"
    assert SEGMENT_DISPLAY_NAMES["AU"] == "Autism"
    assert SEGMENT_DISPLAY_NAMES["AH"] == "AuDHD"
    assert SEGMENT_DISPLAY_NAMES["NT"] == "Neurotypical"
    assert SEGMENT_DISPLAY_NAMES["CU"] == "Custom"


def test_all_segments_have_display_names():
    """Test that all segment codes have display names."""
    for code in SEGMENT_CODES:
        assert code in SEGMENT_DISPLAY_NAMES


# =============================================================================
# Test: Consent Texts
# =============================================================================


def test_consent_texts_contain_all_languages():
    """Test that consent texts exist for all supported languages."""
    assert "en" in CONSENT_TEXTS
    assert "de" in CONSENT_TEXTS
    assert "sr" in CONSENT_TEXTS
    assert "el" in CONSENT_TEXTS


def test_consent_text_mentions_gdpr():
    """Test that English consent text mentions data processing."""
    text = CONSENT_TEXTS["en"]
    assert "data" in text.lower() or "processing" in text.lower()


def test_default_language_is_english():
    """Test that default language is English."""
    assert DEFAULT_LANGUAGE == "en"


# =============================================================================
# Test: Initialization
# =============================================================================


def test_onboarding_flow_initialization(onboarding_flow: OnboardingFlow):
    """Test that OnboardingFlow initializes correctly."""
    assert onboarding_flow is not None
    assert len(onboarding_flow._steps) == 5  # 5 steps in onboarding


# =============================================================================
# Test: Keyboard Generation
# =============================================================================


def test_language_keyboard(onboarding_flow: OnboardingFlow):
    """Test language selection keyboard generation."""
    keyboard = onboarding_flow._language_keyboard()
    assert len(keyboard) == 4  # 4 languages
    assert all(isinstance(row[0], InlineKeyboardButton) for row in keyboard)


def test_segment_keyboard(onboarding_flow: OnboardingFlow):
    """Test segment selection keyboard generation."""
    keyboard = onboarding_flow._segment_keyboard()
    assert len(keyboard) == 5  # 5 segments
    assert all(isinstance(row[0], InlineKeyboardButton) for row in keyboard)


def test_segment_keyboard_uses_display_names(onboarding_flow: OnboardingFlow):
    """Test that segment keyboard uses display names, not internal codes."""
    keyboard = onboarding_flow._segment_keyboard()
    button_texts = [row[0].text for row in keyboard]
    assert "ADHD" in button_texts
    assert "Autism" in button_texts
    assert "AuDHD" in button_texts
    # Should NOT contain internal codes
    assert "AD" not in button_texts
    assert "AU" not in button_texts


def test_consent_keyboard(onboarding_flow: OnboardingFlow):
    """Test consent acceptance keyboard generation."""
    keyboard = onboarding_flow._consent_keyboard()
    assert len(keyboard) == 2  # 2 options: I Agree / I Do Not Agree
    assert all(isinstance(row[0], InlineKeyboardButton) for row in keyboard)


# =============================================================================
# Test: Input Validation
# =============================================================================


def test_validate_name_accepts_valid_name(onboarding_flow: OnboardingFlow):
    """Test that _validate_name accepts valid names."""
    assert onboarding_flow._validate_name("John") is True
    assert onboarding_flow._validate_name("Alice Smith") is True
    assert onboarding_flow._validate_name("李明") is True  # Unicode


def test_validate_name_rejects_empty_string(onboarding_flow: OnboardingFlow):
    """Test that _validate_name rejects empty strings."""
    assert onboarding_flow._validate_name("") is False
    assert onboarding_flow._validate_name("   ") is False


def test_validate_name_rejects_too_long(onboarding_flow: OnboardingFlow):
    """Test that _validate_name rejects names > 100 characters."""
    long_name = "A" * 101
    assert onboarding_flow._validate_name(long_name) is False


def test_validate_name_accepts_max_length(onboarding_flow: OnboardingFlow):
    """Test that _validate_name accepts names exactly 100 characters."""
    max_name = "A" * 100
    assert onboarding_flow._validate_name(max_name) is True


# =============================================================================
# Test: Input Transformation
# =============================================================================


def test_transform_name_strips_whitespace(onboarding_flow: OnboardingFlow):
    """Test that _transform_name strips leading/trailing whitespace."""
    assert onboarding_flow._transform_name("  John  ") == "John"
    assert onboarding_flow._transform_name("\tAlice\n") == "Alice"


# =============================================================================
# Test: State Persistence (Redis with Fallback)
# =============================================================================


@pytest.mark.asyncio
async def test_get_state_fallback_when_redis_unavailable(onboarding_flow: OnboardingFlow):
    """Test that _get_state falls back to in-memory when Redis is unavailable."""
    user_hash = "test_hash"
    onboarding_flow._states_fallback[user_hash] = OnboardingStates.NAME

    # Mock Redis to raise exception
    with patch.object(onboarding_flow._redis, 'get', side_effect=Exception("Redis unavailable")):
        state = await onboarding_flow._get_state(user_hash)
        assert state == OnboardingStates.NAME


@pytest.mark.asyncio
async def test_set_state_uses_redis(onboarding_flow: OnboardingFlow):
    """Test that _set_state persists to Redis."""
    user_hash = "test_hash"
    with patch.object(onboarding_flow._redis, 'set', new_callable=AsyncMock) as mock_set:
        await onboarding_flow._set_state(user_hash, OnboardingStates.NAME)
        mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_set_state_falls_back_to_memory_on_redis_error(onboarding_flow: OnboardingFlow):
    """Test that _set_state falls back to in-memory on Redis error."""
    user_hash = "test_hash"
    with patch.object(onboarding_flow._redis, 'set', side_effect=Exception("Redis unavailable")):
        await onboarding_flow._set_state(user_hash, OnboardingStates.NAME)
        assert onboarding_flow._states_fallback[user_hash] == OnboardingStates.NAME


@pytest.mark.asyncio
async def test_get_data_fallback_when_redis_unavailable(onboarding_flow: OnboardingFlow):
    """Test that _get_data falls back to in-memory when Redis is unavailable."""
    user_hash = "test_hash"
    test_data = {"language": "en", "name": "Test"}
    onboarding_flow._user_data_fallback[user_hash] = test_data

    with patch.object(onboarding_flow._redis, 'get', side_effect=Exception("Redis unavailable")):
        data = await onboarding_flow._get_data(user_hash)
        assert data == test_data


@pytest.mark.asyncio
async def test_set_data_uses_redis(onboarding_flow: OnboardingFlow):
    """Test that _set_data persists to Redis."""
    user_hash = "test_hash"
    test_data = {"language": "en"}
    with patch.object(onboarding_flow._redis, 'set', new_callable=AsyncMock) as mock_set:
        await onboarding_flow._set_data(user_hash, test_data)
        mock_set.assert_called_once()


# =============================================================================
# Test: Start Onboarding
# =============================================================================


@pytest.mark.asyncio
async def test_start_initializes_language_state(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that start() initializes to LANGUAGE state."""
    with patch.object(onboarding_flow, '_send_prompt', new_callable=AsyncMock):
        await onboarding_flow.start(mock_update_with_message, language="en")

        user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
        state = await onboarding_flow._get_state(user_hash)
        assert state == OnboardingStates.LANGUAGE


@pytest.mark.asyncio
async def test_start_sets_initial_user_data(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that start() sets initial user data."""
    with patch.object(onboarding_flow, '_send_prompt', new_callable=AsyncMock):
        await onboarding_flow.start(mock_update_with_message, language="de")

        user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
        data = await onboarding_flow._get_data(user_hash)
        assert data["language"] == "de"
        assert data["name"] is None
        assert data["segment"] is None
        assert data["consented"] is False


@pytest.mark.asyncio
async def test_start_sends_prompt(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that start() calls _send_prompt."""
    with patch.object(onboarding_flow, '_send_prompt', new_callable=AsyncMock) as mock_prompt:
        await onboarding_flow.start(mock_update_with_message, language="en")
        mock_prompt.assert_called_once()


# =============================================================================
# Test: Callback Handling (FINDING-009: Strict Allowlists)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_callback_language_selection(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test handling language selection callback."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.LANGUAGE)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": None, "segment": None, "consented": False})

    mock_update_with_callback.callback_query.data = "lang_de"

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock):
        step = onboarding_flow._steps[0]  # LANGUAGE step
        await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

        data = await onboarding_flow._get_data(user_hash)
        assert data["language"] == "de"


@pytest.mark.asyncio
async def test_handle_callback_rejects_invalid_language(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test that invalid language codes are rejected (FINDING-009)."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.LANGUAGE)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": None, "segment": None, "consented": False})

    # Try to inject invalid language code
    mock_update_with_callback.callback_query.data = "lang_xx"  # Invalid

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock) as mock_advance:
        step = onboarding_flow._steps[0]
        await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

        # Should NOT advance state
        mock_advance.assert_not_called()


@pytest.mark.asyncio
async def test_handle_callback_segment_selection(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test handling segment selection callback."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.WORKING_STYLE)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": "Test", "segment": None, "consented": False})

    mock_update_with_callback.callback_query.data = "segment_AD"

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock):
        step = onboarding_flow._steps[2]  # WORKING_STYLE step
        await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

        data = await onboarding_flow._get_data(user_hash)
        assert data["segment"] == "AD"


@pytest.mark.asyncio
async def test_handle_callback_rejects_invalid_segment(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test that invalid segment codes are rejected (FINDING-009)."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.WORKING_STYLE)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": "Test", "segment": None, "consented": False})

    # Try to inject invalid segment code
    mock_update_with_callback.callback_query.data = "segment_XX"  # Invalid

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock) as mock_advance:
        step = onboarding_flow._steps[2]
        await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

        # Should NOT advance state
        mock_advance.assert_not_called()


@pytest.mark.asyncio
async def test_handle_callback_consent_accept(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test handling consent acceptance."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.CONSENT)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": "Test", "segment": "AD", "consented": False})

    mock_update_with_callback.callback_query.data = "consent_accept"

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock):
        step = onboarding_flow._steps[3]  # CONSENT step
        await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

        data = await onboarding_flow._get_data(user_hash)
        assert data["consented"] is True


@pytest.mark.asyncio
async def test_handle_callback_consent_reject_stops_onboarding(onboarding_flow: OnboardingFlow, mock_update_with_callback):
    """Test that rejecting consent stops onboarding (CRITICAL: consent is NOT skippable)."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_callback)
    await onboarding_flow._set_state(user_hash, OnboardingStates.CONSENT)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": "Test", "segment": "AD", "consented": False})

    mock_update_with_callback.callback_query.data = "consent_reject"

    step = onboarding_flow._steps[3]
    await onboarding_flow._handle_callback(mock_update_with_callback, user_hash, step)

    # State should be set to COMPLETED (no further processing)
    state = await onboarding_flow._get_state(user_hash)
    assert state == OnboardingStates.COMPLETED

    # Consent should still be False
    data = await onboarding_flow._get_data(user_hash)
    assert data["consented"] is False


# =============================================================================
# Test: Text Handling (Name Input)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_text_name_input(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test handling name text input."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
    await onboarding_flow._set_state(user_hash, OnboardingStates.NAME)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": None, "segment": None, "consented": False})

    mock_update_with_message.message.text = "Alice"

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock):
        step = onboarding_flow._steps[1]  # NAME step
        await onboarding_flow._handle_text(mock_update_with_message, user_hash, step)

        data = await onboarding_flow._get_data(user_hash)
        assert data["name"] == "Alice"


@pytest.mark.asyncio
async def test_handle_text_name_input_strips_whitespace(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that name input is stripped of whitespace."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
    await onboarding_flow._set_state(user_hash, OnboardingStates.NAME)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": None, "segment": None, "consented": False})

    mock_update_with_message.message.text = "  Alice  "

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock):
        step = onboarding_flow._steps[1]
        await onboarding_flow._handle_text(mock_update_with_message, user_hash, step)

        data = await onboarding_flow._get_data(user_hash)
        assert data["name"] == "Alice"


@pytest.mark.asyncio
async def test_handle_text_name_rejects_invalid(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that invalid name input is rejected."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
    await onboarding_flow._set_state(user_hash, OnboardingStates.NAME)
    await onboarding_flow._set_data(user_hash, {"language": "en", "name": None, "segment": None, "consented": False})

    mock_update_with_message.message.text = ""  # Empty name

    with patch.object(onboarding_flow, '_advance_state', new_callable=AsyncMock) as mock_advance:
        step = onboarding_flow._steps[1]
        await onboarding_flow._handle_text(mock_update_with_message, user_hash, step)

        # Should NOT advance state
        mock_advance.assert_not_called()


# =============================================================================
# Test: State Transitions
# =============================================================================


@pytest.mark.asyncio
async def test_advance_state_progresses_to_next_step(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that _advance_state moves to the next onboarding step."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
    await onboarding_flow._set_state(user_hash, OnboardingStates.LANGUAGE)

    with patch.object(onboarding_flow, '_send_prompt', new_callable=AsyncMock):
        await onboarding_flow._advance_state(mock_update_with_message, user_hash)

        state = await onboarding_flow._get_state(user_hash)
        assert state == OnboardingStates.NAME


@pytest.mark.asyncio
async def test_advance_state_at_last_step_completes(onboarding_flow: OnboardingFlow, mock_update_with_message):
    """Test that _advance_state at last step marks onboarding as COMPLETED."""
    user_hash = onboarding_flow._get_user_hash(mock_update_with_message)
    await onboarding_flow._set_state(user_hash, OnboardingStates.CONFIRMATION)

    with patch.object(onboarding_flow, '_send_prompt', new_callable=AsyncMock):
        await onboarding_flow._advance_state(mock_update_with_message, user_hash)

        state = await onboarding_flow._get_state(user_hash)
        assert state == OnboardingStates.COMPLETED


# =============================================================================
# Test: Get User Data
# =============================================================================


@pytest.mark.asyncio
async def test_get_user_data_returns_collected_data(onboarding_flow: OnboardingFlow):
    """Test that get_user_data returns all collected user data."""
    user_hash = "test_hash"
    test_data = {
        "language": "de",
        "name": "Alice",
        "segment": "AU",
        "consented": True,
    }
    await onboarding_flow._set_data(user_hash, test_data)

    data = await onboarding_flow.get_user_data(user_hash)
    assert data == test_data


@pytest.mark.asyncio
async def test_get_user_data_returns_none_when_no_data(onboarding_flow: OnboardingFlow):
    """Test that get_user_data returns None when no data exists."""
    data = await onboarding_flow.get_user_data("nonexistent_hash")
    assert data == {} or data is None
