"""
Tests for production middleware.

Test coverage:
- Security headers middleware
- Correlation ID middleware
- LLM cost limiter middleware
- Request logging middleware
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.middleware import (
    CorrelationIDMiddleware,
    LLMCostLimiterMiddleware,
    SecurityHeadersMiddleware,
    create_security_headers,
    log_request,
)

# =============================================================================
# Security Headers Middleware Tests
# =============================================================================


@pytest.mark.asyncio
async def test_security_headers_middleware() -> None:
    """Test security headers are added to response."""
    middleware = SecurityHeadersMiddleware()

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert "X-Content-Type-Options" in result.headers
    assert result.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Frame-Options" in result.headers
    assert result.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in result.headers
    assert "Content-Security-Policy" in result.headers


@pytest.mark.asyncio
async def test_security_headers_custom_csp() -> None:
    """Test custom CSP policy."""
    custom_csp = "default-src 'self'; script-src 'self' 'unsafe-inline';"
    middleware = SecurityHeadersMiddleware(csp_policy=custom_csp)

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert result.headers["Content-Security-Policy"] == custom_csp


@pytest.mark.asyncio
async def test_security_headers_disable_csp() -> None:
    """Test CSP can be disabled."""
    middleware = SecurityHeadersMiddleware(enable_csp=False)

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert "Content-Security-Policy" not in result.headers


def test_get_headers() -> None:
    """Test get_headers method."""
    middleware = SecurityHeadersMiddleware()
    headers = middleware.get_headers()

    assert isinstance(headers, dict)
    assert "X-Frame-Options" in headers
    assert "X-Content-Type-Options" in headers


def test_create_security_headers() -> None:
    """Test create_security_headers convenience function."""
    headers = create_security_headers()

    assert isinstance(headers, dict)
    assert len(headers) > 0


# =============================================================================
# Correlation ID Middleware Tests
# =============================================================================


@pytest.mark.asyncio
async def test_correlation_id_middleware_generates_id() -> None:
    """Test correlation ID is generated when not present."""
    middleware = CorrelationIDMiddleware()

    mock_request = MagicMock()
    mock_request.headers = {}
    mock_request.state = MagicMock()

    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert "X-Correlation-ID" in result.headers
    assert len(result.headers["X-Correlation-ID"]) == 36  # UUID length


@pytest.mark.asyncio
async def test_correlation_id_middleware_uses_existing() -> None:
    """Test correlation ID uses existing ID from request."""
    middleware = CorrelationIDMiddleware()

    existing_id = "test-correlation-id-123"
    mock_request = MagicMock()
    mock_request.headers = {"X-Correlation-ID": existing_id}
    mock_request.state = MagicMock()

    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert result.headers["X-Correlation-ID"] == existing_id


@pytest.mark.asyncio
async def test_correlation_id_custom_header() -> None:
    """Test custom correlation ID header name."""
    middleware = CorrelationIDMiddleware(header_name="X-Request-ID")

    mock_request = MagicMock()
    mock_request.headers = {}
    mock_request.state = MagicMock()

    mock_response = MagicMock()
    mock_response.headers = {}

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    result = await middleware(mock_request, mock_call_next)

    assert "X-Request-ID" in result.headers


# =============================================================================
# LLM Cost Limiter Middleware Tests
# =============================================================================


@pytest.mark.asyncio
async def test_check_cost_limit_admin_bypass() -> None:
    """Test admin users bypass cost limits."""
    limiter = LLMCostLimiterMiddleware()

    allowed, reason = await limiter.check_cost_limit(
        user_id=1,
        estimated_cost=100.0,
        is_admin=True,
    )

    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_check_cost_limit_no_redis() -> None:
    """Test cost limiter without Redis (disabled)."""
    limiter = LLMCostLimiterMiddleware(redis_client=None)

    allowed, reason = await limiter.check_cost_limit(
        user_id=1,
        estimated_cost=1.0,
        is_admin=False,
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_check_cost_limit_within_limits() -> None:
    """Test cost check within limits."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"0.1")

    limiter = LLMCostLimiterMiddleware(
        redis_client=mock_redis,
        user_hourly_limit=1.0,
        user_daily_limit=5.0,
        global_daily_limit=50.0,
    )

    allowed, reason = await limiter.check_cost_limit(
        user_id=1,
        estimated_cost=0.5,
        is_admin=False,
    )

    assert allowed is True
    assert reason is None


@pytest.mark.asyncio
async def test_check_cost_limit_exceeds_hourly() -> None:
    """Test cost check exceeds hourly limit."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"0.9")

    limiter = LLMCostLimiterMiddleware(
        redis_client=mock_redis,
        user_hourly_limit=1.0,
    )

    allowed, reason = await limiter.check_cost_limit(
        user_id=1,
        estimated_cost=0.5,
        is_admin=False,
    )

    assert allowed is False
    assert "Hourly limit" in reason  # type: ignore[operator]


@pytest.mark.asyncio
async def test_record_cost() -> None:
    """Test recording actual LLM cost."""
    mock_redis = AsyncMock()
    mock_redis.incrbyfloat = AsyncMock()
    mock_redis.expire = AsyncMock()

    limiter = LLMCostLimiterMiddleware(redis_client=mock_redis)

    await limiter.record_cost(user_id=1, actual_cost=0.05)

    # Should be called for global, hourly, and daily keys
    assert mock_redis.incrbyfloat.call_count == 3
    assert mock_redis.expire.call_count == 3


@pytest.mark.asyncio
async def test_get_user_usage() -> None:
    """Test getting user's current usage."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=[b"0.25", b"1.5"])

    limiter = LLMCostLimiterMiddleware(redis_client=mock_redis)

    usage = await limiter.get_user_usage(user_id=1)

    assert usage["hourly"] == 0.25
    assert usage["daily"] == 1.5


@pytest.mark.asyncio
async def test_get_user_usage_no_redis() -> None:
    """Test get_user_usage without Redis."""
    limiter = LLMCostLimiterMiddleware(redis_client=None)

    usage = await limiter.get_user_usage(user_id=1)

    assert usage["hourly"] == 0.0
    assert usage["daily"] == 0.0


# =============================================================================
# Request Logging Middleware Tests
# =============================================================================


@pytest.mark.asyncio
async def test_log_request_success() -> None:
    """Test request logging on success."""
    mock_request = MagicMock()
    mock_request.method = "GET"
    mock_request.url = MagicMock()
    mock_request.url.path = "/health"

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def mock_call_next(request: object) -> MagicMock:
        return mock_response

    with patch("src.infra.middleware.logger") as mock_logger:
        result = await log_request(mock_request, mock_call_next)

        assert result == mock_response
        assert mock_logger.info.called


@pytest.mark.asyncio
async def test_log_request_error() -> None:
    """Test request logging on error."""
    mock_request = MagicMock()
    mock_request.method = "POST"
    mock_request.url = MagicMock()
    mock_request.url.path = "/api/test"

    async def mock_call_next(request: object) -> None:
        raise ValueError("Test error")

    with patch("src.infra.middleware.logger") as mock_logger:
        with pytest.raises(ValueError):
            await log_request(mock_request, mock_call_next)

        assert mock_logger.error.called
