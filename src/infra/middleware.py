"""
Production Middleware for Aurora Sun V1.

Provides middleware components for:
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Correlation ID injection for request tracing
- LLM cost limiting to prevent budget overruns
- Request/response logging

Used by:
- All HTTP endpoints
- Webhook handlers
- API routes

References:
    - ROADMAP.md Phase 4.6 (Production Hardening)
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
    - OWASP Security Headers Best Practices
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Context variable for correlation ID (thread-safe request tracking)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


# =============================================================================
# Security Headers Middleware
# =============================================================================


class SecurityHeadersMiddleware:
    """
    Adds security headers to all HTTP responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: default-src 'self'
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), microphone=(), camera=()

    References:
        - OWASP Secure Headers Project
        - Mozilla Security Headers Guide
    """

    def __init__(
        self,
        hsts_max_age: int = 31536000,  # 1 year
        enable_csp: bool = True,
        csp_policy: str | None = None,
    ):
        """
        Initialize security headers middleware.

        Args:
            hsts_max_age: HSTS max-age in seconds (default: 1 year)
            enable_csp: Enable Content Security Policy
            csp_policy: Custom CSP policy (if None, uses default)
        """
        self.hsts_max_age = hsts_max_age
        self.enable_csp = enable_csp
        self.csp_policy = csp_policy or "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none';"

    async def __call__(
        self,
        request: Any,
        call_next: Callable[[Any], Any],
    ) -> Any:
        """
        Process request and add security headers to response.

        Args:
            request: HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response with security headers added
        """
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers[
            "Strict-Transport-Security"
        ] = f"max-age={self.hsts_max_age}; includeSubDomains; preload"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers[
            "Permissions-Policy"
        ] = "geolocation=(), microphone=(), camera=(), payment=()"

        if self.enable_csp:
            response.headers["Content-Security-Policy"] = self.csp_policy

        return response

    def get_headers(self) -> dict[str, str]:
        """
        Get security headers as a dictionary.

        Returns:
            Dictionary of header name -> value

        Example:
            >>> middleware = SecurityHeadersMiddleware()
            >>> headers = middleware.get_headers()
            >>> print(headers["X-Frame-Options"])
            DENY
        """
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": f"max-age={self.hsts_max_age}; includeSubDomains; preload",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
        }

        if self.enable_csp:
            headers["Content-Security-Policy"] = self.csp_policy

        return headers


# =============================================================================
# Correlation ID Middleware
# =============================================================================


class CorrelationIDMiddleware:
    """
    Injects correlation IDs for request tracing.

    Every request gets a unique UUID that's:
    - Added to response headers (X-Correlation-ID)
    - Logged with every log message during request processing
    - Stored in context variable for access anywhere

    This enables:
    - End-to-end request tracing
    - Log aggregation across services
    - Performance profiling
    - Error tracking

    References:
        - Distributed tracing best practices
        - OpenTelemetry correlation IDs
    """

    def __init__(
        self,
        header_name: str = "X-Correlation-ID",
        generate_if_missing: bool = True,
    ):
        """
        Initialize correlation ID middleware.

        Args:
            header_name: HTTP header name for correlation ID
            generate_if_missing: Generate new ID if not provided in request
        """
        self.header_name = header_name
        self.generate_if_missing = generate_if_missing

    async def __call__(
        self,
        request: Any,
        call_next: Callable[[Any], Any],
    ) -> Any:
        """
        Process request and inject correlation ID.

        Args:
            request: HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response with correlation ID header
        """
        # Extract or generate correlation ID
        correlation_id = self._get_or_generate_correlation_id(request)

        # Store in context variable for access anywhere
        correlation_id_var.set(correlation_id)

        # Add to request for handlers
        if hasattr(request, "state"):
            request.state.correlation_id = correlation_id

        # Log request with correlation ID
        # Extract path safely
        path: str | None = None
        if hasattr(request, "url"):
            url = getattr(request, "url", None)
            if url is not None and hasattr(url, "path"):
                path = url.path

        logger.info(
            "request_started",
            extra={
                "correlation_id": correlation_id,
                "method": getattr(request, "method", None),
                "path": path,
            },
        )

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers[self.header_name] = correlation_id

        return response

    def _get_or_generate_correlation_id(self, request: Any) -> str:
        """
        Get correlation ID from request or generate new one.

        Args:
            request: HTTP request

        Returns:
            Correlation ID (UUID string)
        """
        # Try to get from request headers
        if hasattr(request, "headers"):
            correlation_id = request.headers.get(self.header_name)
            if correlation_id:
                return str(correlation_id)

        # Generate new ID if configured
        if self.generate_if_missing:
            return str(uuid.uuid4())

        # Fallback
        return "unknown"


def get_correlation_id() -> str | None:
    """
    Get current request's correlation ID.

    Returns:
        Correlation ID if available, None otherwise

    Example:
        >>> correlation_id = get_correlation_id()
        >>> logger.info("Processing request", extra={"correlation_id": correlation_id})
    """
    return correlation_id_var.get()


# =============================================================================
# LLM Cost Limiter Middleware
# =============================================================================


class LLMCostLimiterMiddleware:
    """
    Limits LLM API costs to prevent budget overruns.

    Enforces:
    - Per-user hourly cost limits
    - Per-user daily cost limits
    - Global daily cost limits
    - Admin override capability

    Uses Redis for distributed cost tracking across instances.

    Example limits:
    - User: $0.50/hour, $5.00/day
    - System: $50.00/day
    - Admin: no limits

    References:
        - ROADMAP.md Phase 4.6 (LLM cost limiter middleware)
    """

    def __init__(
        self,
        redis_client: Any = None,
        user_hourly_limit: float = 0.50,
        user_daily_limit: float = 5.00,
        global_daily_limit: float = 50.00,
    ):
        """
        Initialize LLM cost limiter.

        Args:
            redis_client: Redis client for distributed tracking
            user_hourly_limit: Per-user hourly limit in USD
            user_daily_limit: Per-user daily limit in USD
            global_daily_limit: Global daily limit in USD
        """
        self.redis_client = redis_client
        self.user_hourly_limit = user_hourly_limit
        self.user_daily_limit = user_daily_limit
        self.global_daily_limit = global_daily_limit

    async def check_cost_limit(
        self,
        user_id: int,
        estimated_cost: float,
        is_admin: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Check if user can make an LLM call within cost limits.

        Args:
            user_id: User ID
            estimated_cost: Estimated cost of the call in USD
            is_admin: Whether user is admin (bypasses limits)

        Returns:
            Tuple of (allowed: bool, reason: str | None)
            If allowed=False, reason contains error message

        Example:
            >>> allowed, reason = await limiter.check_cost_limit(123, 0.05)
            >>> if not allowed:
            ...     raise Exception(f"Cost limit exceeded: {reason}")
        """
        if is_admin:
            return True, None

        if self.redis_client is None:
            logger.warning("Redis client not configured, cost limiting disabled")
            return True, None

        # Check global daily limit
        global_key = f"llm_cost:global:daily:{datetime.now(UTC).date()}"
        global_cost = await self._get_cost(global_key)
        if global_cost + estimated_cost > self.global_daily_limit:
            return False, f"Global daily limit (${self.global_daily_limit}) exceeded"

        # Check user hourly limit
        hourly_key = f"llm_cost:user:{user_id}:hourly:{datetime.now(UTC).strftime('%Y-%m-%d-%H')}"
        hourly_cost = await self._get_cost(hourly_key)
        if hourly_cost + estimated_cost > self.user_hourly_limit:
            return False, f"Hourly limit (${self.user_hourly_limit}) exceeded"

        # Check user daily limit
        daily_key = f"llm_cost:user:{user_id}:daily:{datetime.now(UTC).date()}"
        daily_cost = await self._get_cost(daily_key)
        if daily_cost + estimated_cost > self.user_daily_limit:
            return False, f"Daily limit (${self.user_daily_limit}) exceeded"

        return True, None

    async def record_cost(
        self,
        user_id: int,
        actual_cost: float,
    ) -> None:
        """
        Record actual LLM API cost after call completes.

        Args:
            user_id: User ID
            actual_cost: Actual cost of the call in USD
        """
        if self.redis_client is None:
            return

        now = datetime.now(UTC)

        # Increment global daily cost
        global_key = f"llm_cost:global:daily:{now.date()}"
        await self._increment_cost(global_key, actual_cost, ttl_seconds=86400)  # 24 hours

        # Increment user hourly cost
        hourly_key = f"llm_cost:user:{user_id}:hourly:{now.strftime('%Y-%m-%d-%H')}"
        await self._increment_cost(hourly_key, actual_cost, ttl_seconds=3600)  # 1 hour

        # Increment user daily cost
        daily_key = f"llm_cost:user:{user_id}:daily:{now.date()}"
        await self._increment_cost(daily_key, actual_cost, ttl_seconds=86400)  # 24 hours

    async def get_user_usage(
        self,
        user_id: int,
    ) -> dict[str, float]:
        """
        Get user's current LLM cost usage.

        Args:
            user_id: User ID

        Returns:
            Dictionary with 'hourly' and 'daily' costs in USD

        Example:
            >>> usage = await limiter.get_user_usage(123)
            >>> print(f"Used ${usage['daily']:.2f} today")
        """
        if self.redis_client is None:
            return {"hourly": 0.0, "daily": 0.0}

        now = datetime.now(UTC)

        hourly_key = f"llm_cost:user:{user_id}:hourly:{now.strftime('%Y-%m-%d-%H')}"
        daily_key = f"llm_cost:user:{user_id}:daily:{now.date()}"

        hourly_cost = await self._get_cost(hourly_key)
        daily_cost = await self._get_cost(daily_key)

        return {
            "hourly": hourly_cost,
            "daily": daily_cost,
        }

    async def _get_cost(self, key: str) -> float:
        """Get cost from Redis."""
        try:
            value = await self.redis_client.get(key)
            return float(value) if value else 0.0
        except Exception:
            logger.exception(f"Error getting cost for key {key}")
            return 0.0

    async def _increment_cost(
        self,
        key: str,
        amount: float,
        ttl_seconds: int,
    ) -> None:
        """Increment cost in Redis with TTL."""
        try:
            await self.redis_client.incrbyfloat(key, amount)
            await self.redis_client.expire(key, ttl_seconds)
        except Exception:
            logger.exception(f"Error incrementing cost for key {key}")


# =============================================================================
# Request Logging Middleware
# =============================================================================


async def log_request(
    request: Any,
    call_next: Callable[[Any], Any],
) -> Any:
    """
    Log all requests with timing and correlation ID.

    Args:
        request: HTTP request
        call_next: Next middleware/handler in chain

    Returns:
        Response with logging
    """
    start_time = datetime.now(UTC)
    correlation_id = get_correlation_id()

    try:
        response = await call_next(request)
        duration = (datetime.now(UTC) - start_time).total_seconds()

        # Extract path safely
        path: str | None = None
        if hasattr(request, "url"):
            url = getattr(request, "url", None)
            if url is not None and hasattr(url, "path"):
                path = url.path

        logger.info(
            "request_completed",
            extra={
                "correlation_id": correlation_id,
                "method": getattr(request, "method", None),
                "path": path,
                "status_code": getattr(response, "status_code", None),
                "duration_seconds": duration,
            },
        )

        return response

    except Exception as e:
        duration = (datetime.now(UTC) - start_time).total_seconds()

        # Extract path safely
        path_err: str | None = None
        if hasattr(request, "url"):
            url_err = getattr(request, "url", None)
            if url_err is not None and hasattr(url_err, "path"):
                path_err = url_err.path

        logger.error(
            "request_failed",
            extra={
                "correlation_id": correlation_id,
                "method": getattr(request, "method", None),
                "path": path_err,
                "error": str(e),
                "duration_seconds": duration,
            },
            exc_info=True,
        )

        raise


# =============================================================================
# Convenience Functions
# =============================================================================


def create_security_headers() -> dict[str, str]:
    """
    Create security headers dictionary for manual application.

    Returns:
        Dictionary of security headers

    Example:
        >>> headers = create_security_headers()
        >>> response.headers.update(headers)
    """
    middleware = SecurityHeadersMiddleware()
    return middleware.get_headers()


# =============================================================================
# SEC-008: HTTPS Redirect Middleware (production only)
# =============================================================================


class HTTPSRedirectMiddleware:
    """Redirect HTTP to HTTPS in production.

    Checks X-Forwarded-Proto header (set by reverse proxy / Caddy)
    to determine the original protocol. Only active when registered
    in src/api/__init__.py (production environment only).
    """

    async def __call__(
        self,
        request: Any,
        call_next: Callable[[Any], Any],
    ) -> Any:
        """Check protocol and redirect HTTP to HTTPS."""
        forwarded_proto = None
        if hasattr(request, "headers"):
            forwarded_proto = request.headers.get("x-forwarded-proto")

        url_scheme = None
        if hasattr(request, "url") and hasattr(request.url, "scheme"):
            url_scheme = request.url.scheme

        if forwarded_proto == "http" or (
            forwarded_proto is None and url_scheme == "http"
        ):
            from starlette.responses import RedirectResponse

            https_url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=https_url, status_code=301)

        return await call_next(request)
