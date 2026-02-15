"""
Authentication and Authorization for Aurora Sun V1 REST API.

Implements:
- JWT token-based authentication (via PyJWT)
- User identification via token
- Rate limiting
- Request verification
- Startup secrets validation (fail-fast if missing)

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt

from src.lib.security import hash_uid

logger = logging.getLogger(__name__)


@dataclass
class AuthToken:
    """
    JWT authentication token.

    Contains user identification and expiry information.
    """

    user_id: int
    telegram_id: int
    issued_at: datetime
    expires_at: datetime
    token_type: str = "Bearer"

    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(UTC) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "user_id": self.user_id,
            "telegram_id": self.telegram_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "token_type": self.token_type,
        }


@dataclass
class RateLimitInfo:
    """Rate limit information for a user."""

    user_id: int
    requests_made: int
    window_start: datetime
    limit: int = 1000  # Requests per window
    window_seconds: int = 3600  # 1 hour window

    def is_exceeded(self) -> bool:
        """Check if rate limit is exceeded."""
        # Reset if window has passed
        if datetime.now(UTC) >= self.window_start + timedelta(seconds=self.window_seconds):
            return False
        return self.requests_made >= self.limit

    def increment(self) -> None:
        """Increment request counter."""
        now = datetime.now(UTC)
        # Reset if window has passed
        if now >= self.window_start + timedelta(seconds=self.window_seconds):
            self.requests_made = 0
            self.window_start = now

        self.requests_made += 1


class AuthService:
    """
    Authentication service for REST API.

    Handles:
    - Token generation
    - Token validation
    - Rate limiting
    - Request authentication
    """

    # Token expiry: 30 days
    TOKEN_EXPIRY_DAYS = 30

    # Rate limit: 1000 requests per hour per user
    RATE_LIMIT = 1000
    RATE_LIMIT_WINDOW_SECONDS = 3600

    # Maximum entries in the rate limit dictionary to prevent
    # unbounded memory growth. When exceeded, oldest 20% are evicted.
    MAX_RATE_LIMIT_ENTRIES = 10000

    def __init__(self, secret_key: str | None = None) -> None:
        """
        Initialize auth service.

        No hardcoded fallback secret. If AURORA_API_SECRET_KEY
        is not set and no explicit key is provided, raise RuntimeError.

        Args:
            secret_key: Secret key for token signing (from env if not provided)

        Raises:
            RuntimeError: If no secret key is available
        """
        resolved_key = secret_key or os.getenv("AURORA_API_SECRET_KEY")
        if not resolved_key:
            raise RuntimeError(
                "AURORA_API_SECRET_KEY environment variable is required. "
                "Set it to a cryptographically random string."
            )
        self.secret_key: str = resolved_key
        self._rate_limits: dict[int, RateLimitInfo] = {}

    def _evict_stale_rate_limits(self) -> None:
        """
        Evict oldest 20% of rate limit entries when the dict
        exceeds MAX_RATE_LIMIT_ENTRIES. Entries are sorted by window_start
        so the oldest (least recently active) are removed first.
        """
        if len(self._rate_limits) <= self.MAX_RATE_LIMIT_ENTRIES:
            return

        # Sort by window_start (oldest first) and remove oldest 20%
        sorted_entries = sorted(
            self._rate_limits.items(),
            key=lambda item: item[1].window_start,
        )
        evict_count = len(sorted_entries) // 5  # 20%
        for user_id, _ in sorted_entries[:evict_count]:
            del self._rate_limits[user_id]

        logger.info(
            "Rate limit eviction: removed %d entries, %d remaining",
            evict_count,
            len(self._rate_limits),
        )

    def generate_token(self, user_id: int, telegram_id: int) -> AuthToken:
        """
        Generate a JWT token for a user.

        Args:
            user_id: User ID
            telegram_id: Telegram ID

        Returns:
            Auth token
        """
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=self.TOKEN_EXPIRY_DAYS)

        token = AuthToken(
            user_id=user_id,
            telegram_id=telegram_id,
            issued_at=now,
            expires_at=expires_at,
        )

        logger.info("Generated token for user_hash=%s", hash_uid(user_id))
        return token

    def encode_token(self, token: AuthToken) -> str:
        """
        Encode token to JWT string using PyJWT.

        Args:
            token: Auth token

        Returns:
            JWT string
        """
        payload: dict[str, Any] = {
            "sub": str(token.user_id),
            "telegram_id": token.telegram_id,
            "iat": token.issued_at,
            "exp": token.expires_at,
            "type": token.token_type,
        }
        return pyjwt.encode(payload, self.secret_key, algorithm="HS256")

    def decode_token(self, jwt_token: str) -> AuthToken | None:
        """
        Decode JWT token using PyJWT.

        Args:
            jwt_token: JWT string

        Returns:
            Auth token, or None if invalid
        """
        try:
            payload = pyjwt.decode(
                jwt_token, self.secret_key, algorithms=["HS256"]
            )

            token = AuthToken(
                user_id=int(payload["sub"]),
                telegram_id=payload["telegram_id"],
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                token_type=payload.get("type", "Bearer"),
            )

            return token

        except pyjwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except pyjwt.InvalidTokenError as e:
            logger.error("Token decode error: %s", e)
            return None

    def authenticate_request(self, authorization_header: str | None) -> AuthToken | None:
        """
        Authenticate a request using Authorization header.

        Args:
            authorization_header: Authorization header value (e.g., "Bearer <token>")

        Returns:
            Auth token if valid, None otherwise
        """
        if not authorization_header:
            return None

        # Parse Bearer token
        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning("Invalid Authorization header format")
            return None

        jwt_token = parts[1]
        return self.decode_token(jwt_token)

    def check_rate_limit(self, user_id: int) -> bool:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: User ID

        Returns:
            True if within limit, False if exceeded
        """
        # Evict stale entries before adding new ones (memory bound enforcement)
        self._evict_stale_rate_limits()

        if user_id not in self._rate_limits:
            self._rate_limits[user_id] = RateLimitInfo(
                user_id=user_id,
                requests_made=0,
                window_start=datetime.now(UTC),
                limit=self.RATE_LIMIT,
                window_seconds=self.RATE_LIMIT_WINDOW_SECONDS,
            )

        rate_limit = self._rate_limits[user_id]
        if rate_limit.is_exceeded():
            logger.warning("Rate limit exceeded for user_hash=%s", hash_uid(user_id))
            return False

        rate_limit.increment()
        return True

    def get_rate_limit_info(self, user_id: int) -> RateLimitInfo | None:
        """
        Get rate limit info for a user.

        Args:
            user_id: User ID

        Returns:
            Rate limit info, or None if not tracked
        """
        return self._rate_limits.get(user_id)


def validate_secrets() -> None:
    """
    Validate that required secrets are set at startup (fail-fast).

    Checks AURORA_MASTER_KEY, AURORA_HMAC_SECRET, and AURORA_API_SECRET_KEY
    are present and non-empty. In dev mode (AURORA_DEV_MODE=1), AURORA_MASTER_KEY
    is only warned about (it has its own dev fallback in EncryptionService).

    Raises:
        RuntimeError: If any required secret is missing (outside dev exceptions)
    """
    is_dev_mode = os.getenv("AURORA_DEV_MODE") == "1"
    missing: list[str] = []

    # AURORA_MASTER_KEY: warn-only in dev mode (EncryptionService has its own dev fallback)
    master_key = os.getenv("AURORA_MASTER_KEY")
    if not master_key:
        if is_dev_mode:
            logger.warning(
                "AURORA_MASTER_KEY not set. Dev mode fallback will be used. "
                "DO NOT USE IN PRODUCTION."
            )
        else:
            missing.append("AURORA_MASTER_KEY")

    # AURORA_HMAC_SECRET: always required
    if not os.getenv("AURORA_HMAC_SECRET"):
        missing.append("AURORA_HMAC_SECRET")

    # AURORA_API_SECRET_KEY: always required
    if not os.getenv("AURORA_API_SECRET_KEY"):
        missing.append("AURORA_API_SECRET_KEY")

    if missing:
        raise RuntimeError(
            f"Missing required secrets: {', '.join(missing)}. "
            "Set these environment variables before starting the application."
        )

    logger.info("All required secrets validated successfully.")


__all__ = [
    "AuthService",
    "AuthToken",
    "RateLimitInfo",
    "validate_secrets",
]
