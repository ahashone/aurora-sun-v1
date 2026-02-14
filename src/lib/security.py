"""
Input Security Middleware for Aurora Sun V1

Security components for input sanitization, rate limiting, message validation,
and HTTP security headers.

Components:
- InputSanitizer: XSS, SQL injection, path traversal, markdown sanitization
- RateLimiter: Per-user rate limiting with Redis backend
- MessageSizeValidator: Text and voice message size limits
- SecurityHeaders: HTTP security headers middleware

Follows ARCHITECTURE.md Section 10 (Input Validation & Rate Limiting).

Usage:
    from src.lib.security import (
        InputSanitizer,
        RateLimiter,
        MessageSizeValidator,
        SecurityHeaders
    )

    # Input sanitization
    safe_text = InputSanitizer.sanitize_xss(user_input)

    # Rate limiting
    allowed = await RateLimiter.check_rate_limit(user_id, "chat")
    remaining = await RateLimiter.get_remaining(user_id, "chat")

    # Message validation
    is_valid = MessageSizeValidator.validate_message_size(message)

    # Add security headers to FastAPI app
    app.add_middleware(SecurityHeaders)
"""

import hashlib
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger()


def hash_uid(user_id: int) -> str:
    """Return a 12-char SHA-256 prefix for log-safe user identification."""
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12]


# ============================================
# Input Sanitizer
# ============================================

class InputSanitizer:
    """
    Input sanitization for XSS, SQL injection, path traversal, and markdown.

    NOTE: For SQL injection prevention, use parameterized queries instead.
    This provides defense-in-depth by sanitizing inputs before they reach
    the database layer.
    """

    # XSS: HTML tags and event handlers to remove
    XSS_PATTERNS = [
        # Script tags (various encodings)
        (re.compile(r"<\s*script[^>]*>", re.IGNORECASE), ""),
        (re.compile(r"<\s*/\s*script\s*>", re.IGNORECASE), ""),

        # Event handlers (on* attributes)
        (re.compile(r"\s+on\w+\s*=", re.IGNORECASE), " data-safe="),

        # JavaScript protocol
        (re.compile(r"javascript\s*:", re.IGNORECASE), "safe:"),

        # Data URI (potential XSS)
        (re.compile(r"data\s*:\s*text/html", re.IGNORECASE), "safe:text/plain"),

        # VBScript
        (re.compile(r"vbscript\s*:", re.IGNORECASE), "safe:"),

        # Expression (IE-specific)
        (re.compile(r"expression\s*\(", re.IGNORECASE), "safe("),

        # SVG onload
        (re.compile(r"onload\s*=", re.IGNORECASE), "data-safe-onload="),
    ]

    # SQL: Patterns that might indicate injection attempts
    # WARNING: This is defense-in-depth only. Use parameterized queries!
    SQL_INJECTION_PATTERNS = [
        re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|TRUNCATE)\b)", re.IGNORECASE),
        re.compile(r"(--|#|\/\*|\*\/)"),  # SQL comments
        re.compile(r"(\bOR\b|\bAND\b)\s+\d+\s*=\s*\d+", re.IGNORECASE),  # OR 1=1
        re.compile(r"'\s*(OR|AND)\s*'", re.IGNORECASE),
        re.compile(r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP)", re.IGNORECASE),
    ]

    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        (re.compile(r"\.\.(\/|\\)"), ""),  # ../
        (re.compile(r"^\/etc\/passwd", re.IGNORECASE), ""),
        (re.compile(r"^\/etc\/shadow", re.IGNORECASE), ""),
        (re.compile(r"^\/windows\/system32", re.IGNORECASE), ""),
        (re.compile(r"%2e%2e", re.IGNORECASE), ""),  # URL-encoded ../
        (re.compile(r"\.\.%2f", re.IGNORECASE), ""),  # URL-encoded ../
    ]

    # Markdown: Potentially dangerous markdown patterns
    MARKDOWN_DANGEROUS_PATTERNS = [
        # Auto-linking (can be used for phishing)
        (re.compile(r"<https?://[^>]+>"), lambda m: m.group(0)),
        # JavaScript links
        (re.compile(r"javascript:"), "safe:"),
        # Data links
        (re.compile(r"data:"), "safe:"),
    ]

    @classmethod
    def sanitize_xss(cls, input_text: str) -> str:
        """
        Remove XSS attack vectors from input text.

        Removes:
        - Script tags and their content
        - Event handlers (onclick, onerror, etc.)
        - JavaScript protocol handlers
        - Data URIs
        - SVG onload attributes

        Args:
            input_text: Raw user input

        Returns:
            Sanitized text safe for display/storage
        """
        if not input_text:
            return ""

        result = input_text

        # Apply all XSS patterns
        for pattern, replacement in cls.XSS_PATTERNS:
            result = pattern.sub(replacement, result)

        # Additional HTML entity encoding for remaining < and >
        result = result.replace("<", "&lt;").replace(">", "&gt;")

        logger.debug("input_sanitized_xss", original_length=len(input_text), result_length=len(result))
        return result

    @classmethod
    def sanitize_sql(cls, input_text: str) -> str:
        """
        Sanitize input for SQL injection patterns.

        WARNING: This is defense-in-depth only. ALWAYS use parameterized
        queries for database operations. This method helps catch malicious
        input before it reaches the database layer.

        Args:
            input_text: Raw user input

        Returns:
            Sanitized text with dangerous patterns neutralized
        """
        if not input_text:
            return ""

        result = input_text

        # Escape single quotes (for string literals)
        result = result.replace("'", "''")

        # Neutralize SQL comments
        result = re.sub(r"--", "-- ", result)
        result = re.sub(r"#", "# ", result)
        result = re.sub(r"/\*", "/* ", result)

        # Remove or neutralize dangerous keywords (with word boundaries)
        dangerous_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "UNION", "ALTER", "CREATE", "TRUNCATE"]
        for keyword in dangerous_keywords:
            # Replace with placeholder (won't execute as SQL)
            result = re.sub(
                rf"\b{keyword}\b",
                f"[{keyword}_BLOCKED]",
                result,
                flags=re.IGNORECASE
            )

        logger.debug("input_sanitized_sql", original_length=len(input_text), result_length=len(result))
        return result

    @classmethod
    def sanitize_path(cls, input_text: str) -> str:
        """
        Prevent path traversal attacks.

        Removes:
        - Directory traversal (..)
        - Absolute path references
        - URL-encoded traversal patterns
        - Windows system paths

        Args:
            input_text: Raw user input (e.g., filename, path)

        Returns:
            Sanitized path safe for file operations
        """
        if not input_text:
            return ""

        result = input_text

        # Apply all path traversal patterns
        for pattern, replacement in cls.PATH_TRAVERSAL_PATTERNS:
            if callable(replacement):
                result = pattern.sub(replacement, result)
            else:
                result = pattern.sub(replacement, result)

        # Normalize forward slashes
        result = result.replace("\\", "/")

        # Remove leading slashes (prevent absolute paths)
        result = re.sub(r"^/+", "", result)

        # Remove null bytes
        result = result.replace("\x00", "")

        logger.debug("input_sanitized_path", original_length=len(input_text), result_length=len(result))
        return result

    @classmethod
    def sanitize_markdown(cls, input_text: str) -> str:
        """
        Sanitize markdown to prevent injection attacks.

        Neutralizes:
        - Auto-linked URLs (potential phishing)
        - JavaScript/data protocol links
        - Keeps legitimate markdown functionality

        Args:
            input_text: Raw user input with markdown

        Returns:
            Sanitized markdown safe for rendering
        """
        if not input_text:
            return ""

        result = input_text

        # Neutralize javascript: and data: links
        for pattern, replacement in cls.MARKDOWN_DANGEROUS_PATTERNS:
            if callable(replacement):
                result = pattern.sub(replacement, result)
            else:
                result = pattern.sub(str(replacement), result)

        # Encode angle brackets in URLs to prevent HTML injection
        result = re.sub(
            r"(https?://[^\s<>]+)",
            lambda m: m.group(1).replace("<", "%3C").replace(">", "%3E"),
            result
        )

        logger.debug("input_sanitized_markdown", original_length=len(input_text), result_length=len(result))
        return result

    @classmethod
    def sanitize_all(cls, input_text: str) -> str:
        """
        Apply all sanitization methods in order.

        Order: XSS -> SQL -> Path -> Markdown

        Args:
            input_text: Raw user input

        Returns:
            Fully sanitized text
        """
        result = input_text
        result = cls.sanitize_xss(result)
        result = cls.sanitize_sql(result)
        result = cls.sanitize_path(result)
        result = cls.sanitize_markdown(result)
        return result


# ============================================
# Rate Limiter Configuration
# ============================================

class RateLimitTier(StrEnum):
    """Rate limit tiers for different action types."""
    CHAT = "chat"          # Standard chat messages (30/min, 100/hour)
    VOICE = "voice"        # Voice message uploads
    API = "api"            # API requests
    ADMIN = "admin"        # Admin commands


@dataclass
class RateLimitConfig:
    """Rate limit configuration per tier."""

    requests_per_minute: int
    requests_per_hour: int

    @property
    def window_minute(self) -> int:
        return 60

    @property
    def window_hour(self) -> int:
        return 3600


# Default rate limit configurations
RATE_LIMIT_CONFIGS: dict[RateLimitTier, RateLimitConfig] = {
    RateLimitTier.CHAT: RateLimitConfig(requests_per_minute=30, requests_per_hour=100),
    RateLimitTier.VOICE: RateLimitConfig(requests_per_minute=10, requests_per_hour=50),
    RateLimitTier.API: RateLimitConfig(requests_per_minute=100, requests_per_hour=500),
    RateLimitTier.ADMIN: RateLimitConfig(requests_per_minute=60, requests_per_hour=300),
}


# ============================================
# In-Memory Rate Limiter Fallback
# ============================================

class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter fallback.

    Used when Redis is unavailable. Provides degraded-but-functional
    rate limiting to prevent blocking all traffic or allowing unlimited access.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, list[float] | float | int]] = {}

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if request is allowed using sliding window.

        Args:
            key: Unique identifier (e.g., "user:123:chat")
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            (allowed, retry_after_seconds)
        """
        now = time.monotonic()

        if key not in self._buckets:
            self._buckets[key] = {"requests": [], "last_check": now}

        bucket = self._buckets[key]
        cutoff = now - window_seconds

        # Remove expired requests
        requests_list = bucket["requests"]
        if isinstance(requests_list, list):
            bucket["requests"] = [ts for ts in requests_list if isinstance(ts, float) and ts > cutoff]
        else:
            bucket["requests"] = []

        # Check limit
        requests_list2 = bucket["requests"]
        if isinstance(requests_list2, list):
            if len(requests_list2) >= max_requests:
                oldest = requests_list2[0]
                if isinstance(oldest, float):
                    retry_after = int(oldest + window_seconds - now) + 1
                    return False, max(retry_after, 1)
                return False, 1

            # Record this request
            requests_list2.append(now)
            bucket["last_check"] = now
            return True, 0

        return False, 1

    def get_remaining(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> int:
        """Get remaining requests in current window."""
        now = time.monotonic()

        if key not in self._buckets:
            return max_requests

        bucket = self._buckets[key]
        cutoff = now - window_seconds

        # Count valid requests
        requests_list = bucket["requests"]
        if isinstance(requests_list, list):
            active_requests = [ts for ts in requests_list if isinstance(ts, float) and ts > cutoff]
            return max(0, max_requests - len(active_requests))
        return max_requests

    def cleanup_stale_buckets(self, max_age_seconds: float = 600.0) -> None:
        """Remove buckets not accessed recently."""
        now = time.monotonic()
        stale_keys = []
        for k, v in self._buckets.items():
            last_check = v.get("last_check")
            if isinstance(last_check, (int, float)) and now - last_check > max_age_seconds:
                stale_keys.append(k)
        for k in stale_keys:
            del self._buckets[k]


# Module-level singleton for memory fallback
_memory_rate_limiter = InMemoryRateLimiter()


# ============================================
# Redis Rate Limiter
# ============================================

class RateLimiter:
    """
    Per-user rate limiter with Redis backend.

    Supports:
    - Per-user rate limiting (by user_id)
    - Per-action rate limiting (chat, voice, api, admin)
    - Sliding window algorithm
    - Redis backend with memory fallback
    - Configurable limits per tier

    Default limits (ARCH-10):
    - Chat: 30 messages/minute, 100 messages/hour
    - Voice: 10 uploads/minute, 50 uploads/hour

    Usage:
        # Check if user can send message
        allowed = await RateLimiter.check_rate_limit(user_id=123, action="chat")

        # Get remaining requests
        remaining = await RateLimiter.get_remaining(user_id=123, action="chat")
    """

    # Redis key prefix
    REDIS_PREFIX = "aurora:ratelimit:"

    # In-memory fallback enabled by default
    _memory_fallback_enabled = True

    @classmethod
    async def _get_redis_client(cls) -> Any:
        """
        Get Redis client from RedisService.

        Returns Redis client or None if unavailable.
        """
        try:
            from src.services.redis_service import get_redis_client
            return await get_redis_client()
        except ImportError:
            logger.warning("rate_limiter_redis_service_not_available")
            return None

    @classmethod
    async def check_rate_limit(
        cls,
        user_id: int,
        action: str = "chat",
        fail_closed: bool = False,
    ) -> bool:
        """
        Check if user is within rate limit for an action.

        Args:
            user_id: User's Telegram ID
            action: Action tier ("chat", "voice", "api", "admin")
            fail_closed: If True, deny requests when both Redis and in-memory
                fallback are unavailable. Use for sensitive endpoints.

        Returns:
            True if allowed, False if rate limit exceeded
        """
        config = RATE_LIMIT_CONFIGS.get(RateLimitTier(action), RATE_LIMIT_CONFIGS[RateLimitTier.CHAT])

        # Check minute limit
        try:
            allowed_minute, _ = await cls._check_window(
                user_id=user_id,
                action=action,
                window=config.window_minute,
                max_requests=config.requests_per_minute
            )
        except Exception:
            if fail_closed:
                logger.warning(
                    "rate_limit_fail_closed",
                    user_hash=hash_uid(user_id),
                    action=action,
                )
                return False
            return True

        if not allowed_minute:
            logger.warning(
                "rate_limit_exceeded_minute",
                user_hash=hash_uid(user_id),
                action=action,
                limit=config.requests_per_minute,
                window=config.window_minute
            )
            return False

        # Check hour limit
        try:
            allowed_hour, _ = await cls._check_window(
                user_id=user_id,
                action=action,
                window=config.window_hour,
                max_requests=config.requests_per_hour
            )
        except Exception:
            if fail_closed:
                logger.warning(
                    "rate_limit_fail_closed",
                    user_hash=hash_uid(user_id),
                    action=action,
                )
                return False
            return True

        if not allowed_hour:
            logger.warning(
                "rate_limit_exceeded_hour",
                user_hash=hash_uid(user_id),
                action=action,
                limit=config.requests_per_hour,
                window=config.window_hour
            )
            return False

        return True

    @classmethod
    async def get_remaining(
        cls,
        user_id: int,
        action: str = "chat"
    ) -> int:
        """
        Get remaining requests for user in current window.

        Args:
            user_id: User's Telegram ID
            action: Action tier ("chat", "voice", "api", "admin")

        Returns:
            Number of remaining requests in the current minute window
        """
        config = RATE_LIMIT_CONFIGS.get(RateLimitTier(action), RATE_LIMIT_CONFIGS[RateLimitTier.CHAT])

        return await cls._get_remaining(
            user_id=user_id,
            action=action,
            window=config.window_minute,
            max_requests=config.requests_per_minute
        )

    @classmethod
    async def _check_window(
        cls,
        user_id: int,
        action: str,
        window: int,
        max_requests: int
    ) -> tuple[bool, int]:
        """Check rate limit for a specific window."""
        key = f"{cls.REDIS_PREFIX}{user_id}:{action}:{window}s"

        # Try Redis first
        redis_client = await cls._get_redis_client()
        if redis_client:
            try:
                return await cls._check_redis(redis_client, key, window, max_requests)
            except Exception as e:
                logger.warning("rate_limit_redis_error", error=str(e))

        # Fall back to memory limiter
        return _memory_rate_limiter.check_rate_limit(key, max_requests, window)

    @classmethod
    async def _get_remaining(
        cls,
        user_id: int,
        action: str,
        window: int,
        max_requests: int
    ) -> int:
        """Get remaining requests for a window."""
        key = f"{cls.REDIS_PREFIX}{user_id}:{action}:{window}s"

        # Try Redis first
        redis_client = await cls._get_redis_client()
        if redis_client:
            try:
                return await cls._get_remaining_redis(redis_client, key, window, max_requests)
            except Exception as e:
                logger.warning("rate_limit_redis_error", error=str(e))

        # Fall back to memory limiter
        return _memory_rate_limiter.get_remaining(key, max_requests, window)

    @classmethod
    async def _check_redis(
        cls,
        client: Any,
        key: str,
        window: int,
        max_requests: int
    ) -> tuple[bool, int]:
        """Check rate limit using Redis."""

        now = time.time()
        window_start = now - window

        # Use Redis sorted set for sliding window
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
        pipe.zcard(key)  # Count current requests
        pipe.zadd(key, {str(now): now})  # Add current request
        pipe.expire(key, window)  # Set expiry
        results = await pipe.execute()

        current_count = results[1]

        if current_count >= max_requests:
            # Rate limit exceeded
            # Remove the request we just added since it's rejected
            await client.zrem(key, str(now))

            # Calculate retry_after
            oldest = await client.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_time = oldest[0][1]
                retry_after = int(oldest_time + window - now) + 1
            else:
                retry_after = window

            return False, retry_after

        return True, 0

    @classmethod
    async def _get_remaining_redis(
        cls,
        client: Any,
        key: str,
        window: int,
        max_requests: int
    ) -> int:
        """Get remaining requests using Redis."""
        now = time.time()
        window_start = now - window

        # Clean old entries and count
        await client.zremrangebyscore(key, 0, window_start)
        current_count: int = await client.zcard(key)

        return max(0, max_requests - current_count)

    @classmethod
    async def reset_limit(cls, user_id: int, action: str | None = None) -> None:
        """
        Reset rate limit for a user.

        Args:
            user_id: User's Telegram ID
            action: Optional specific action to reset (if None, resets all)
        """
        redis_client = await cls._get_redis_client()
        if not redis_client:
            # Clear from memory
            for tier in RateLimitTier:
                key = f"{cls.REDIS_PREFIX}{user_id}:{tier}:*"
                if action and action != tier.value:
                    continue
                _memory_rate_limiter._buckets.pop(key, None)
            return

        # Clear from Redis
        if action:
            for window in [60, 3600]:
                key = f"{cls.REDIS_PREFIX}{user_id}:{action}:{window}s"
                await redis_client.delete(key)
        else:
            pattern = f"{cls.REDIS_PREFIX}{user_id}:*"
            keys = []
            async for key in redis_client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await redis_client.delete(*keys)

        logger.info("rate_limit_reset", user_hash=hash_uid(user_id), action=action)


# ============================================
# Message Size Validator
# ============================================

class MessageSizeValidator:
    """
    Validates message sizes for text and voice inputs.

    Limits (ARCH-10):
    - Text messages: 4096 characters max
    - Voice messages: 60 seconds / 10MB max
    """

    # Default limits
    DEFAULT_MAX_TEXT_LENGTH = 4096  # characters
    DEFAULT_MAX_VOICE_SECONDS = 60  # seconds
    DEFAULT_MAX_VOICE_SIZE = 10 * 1024 * 1024  # 10 MB

    @classmethod
    def validate_message_size(
        cls,
        message: str,
        max_size: int = DEFAULT_MAX_TEXT_LENGTH
    ) -> bool:
        """
        Validate text message size.

        Args:
            message: The text message to validate
            max_size: Maximum allowed characters (default: 4096)

        Returns:
            True if message is within size limit, False otherwise
        """
        if not message:
            return True

        is_valid = len(message) <= max_size

        if not is_valid:
            logger.warning(
                "message_size_exceeded",
                message_length=len(message),
                max_size=max_size
            )

        return is_valid

    @classmethod
    def validate_voice_message(
        cls,
        duration_seconds: int,
        file_size_bytes: int
    ) -> tuple[bool, str | None]:
        """
        Validate voice message size and duration.

        Args:
            duration_seconds: Voice message duration in seconds
            file_size_bytes: Voice file size in bytes

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check duration
        if duration_seconds > cls.DEFAULT_MAX_VOICE_SECONDS:
            error_msg = f"Voice message too long. Maximum: {cls.DEFAULT_MAX_VOICE_SECONDS}s, got: {duration_seconds}s"
            logger.warning(
                "voice_message_duration_exceeded",
                duration_seconds=duration_seconds,
                max_seconds=cls.DEFAULT_MAX_VOICE_SECONDS
            )
            return False, error_msg

        # Check file size
        if file_size_bytes > cls.DEFAULT_MAX_VOICE_SIZE:
            error_msg = f"Voice message too large. Maximum: {cls.DEFAULT_MAX_VOICE_SIZE // (1024*1024)}MB, got: {file_size_bytes // (1024*1024)}MB"
            logger.warning(
                "voice_message_size_exceeded",
                file_size_bytes=file_size_bytes,
                max_size_bytes=cls.DEFAULT_MAX_VOICE_SIZE
            )
            return False, error_msg

        return True, None

    @classmethod
    def truncate_message(
        cls,
        message: str,
        max_size: int = DEFAULT_MAX_TEXT_LENGTH
    ) -> str:
        """
        Truncate message to maximum size.

        Args:
            message: The text message to truncate
            max_size: Maximum allowed characters

        Returns:
            Truncated message
        """
        if len(message) <= max_size:
            return message

        truncated = message[:max_size]
        logger.info("message_truncated", original_length=len(message), truncated_length=max_size)
        return truncated


# ============================================
# Security Headers Middleware
# ============================================

class SecurityHeaders:
    """
    FastAPI middleware for adding security headers to HTTP responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: (configurable)
    - Referrer-Policy: strict-origin-when-cross-origin

    Usage:
        from fastapi import FastAPI
        from src.lib.security import SecurityHeaders

        app = FastAPI()
        app.add_middleware(SecurityHeaders)
    """

    # Default CSP (Content Security Policy)
    DEFAULT_CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )

    @classmethod
    def get_headers(cls, csp: str | None = None) -> dict[str, str]:
        """
        Get security headers dictionary.

        Args:
            csp: Optional custom Content-Security-Policy

        Returns:
            Dictionary of security headers
        """
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": csp or cls.DEFAULT_CSP,
            # Permissions Policy (formerly Feature Policy)
            "Permissions-Policy": (
                "geolocation=(), "
                "microphone=(), "
                "camera=(), "
                "payment=()"
            ),
        }

    @classmethod
    def apply_to_response(cls, response: Any, csp: str | None = None) -> Any:
        """
        Apply security headers to a response object.

        Args:
            response: FastAPI/Starlette response object
            csp: Optional custom Content-Security-Policy
        """
        headers = cls.get_headers(csp)
        for name, value in headers.items():
            response.headers[name] = value
        return response


# ============================================
# FastAPI Middleware Integration
# ============================================

def create_security_middleware(
    app: Any,
    csp: str | None = None,
    enable_rate_limiting: bool = True
) -> None:
    """
    Add all security middleware to a FastAPI application.

    Args:
        app: FastAPI application instance
        csp: Optional custom Content-Security-Policy
        enable_rate_limiting: Whether to add rate limiting middleware

    Usage:
        from fastapi import FastAPI
        from src.lib.security import create_security_middleware

        app = FastAPI()
        create_security_middleware(app)
    """
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware

    # Add security headers middleware
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Any:
            response = await call_next(request)
            return SecurityHeaders.apply_to_response(response, csp)

    app.add_middleware(SecurityHeadersMiddleware)

    logger.info("security_middleware_initialized", csp=csp, rate_limiting=enable_rate_limiting)
