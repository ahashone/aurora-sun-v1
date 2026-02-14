"""
Authentication and Authorization for Aurora Sun V1 REST API.

Implements:
- JWT token-based authentication
- User identification via token
- Rate limiting
- Request verification

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

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

    def __init__(self, secret_key: str | None = None) -> None:
        """
        Initialize auth service.

        Args:
            secret_key: Secret key for token signing (from env if not provided)
        """
        self.secret_key: str = secret_key or os.getenv(
            "AURORA_API_SECRET_KEY", "dev-secret-key-change-in-production"
        ) or "dev-secret-key-change-in-production"
        self._rate_limits: dict[int, RateLimitInfo] = {}

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

        logger.info(f"Generated token for user {user_id}")
        return token

    def encode_token(self, token: AuthToken) -> str:
        """
        Encode token to JWT string.

        This is a simplified implementation. In production, use PyJWT library.

        Args:
            token: Auth token

        Returns:
            JWT string
        """
        # Simplified JWT encoding (use PyJWT in production)
        import base64
        import json

        payload = token.to_dict()
        payload_json = json.dumps(payload, default=str)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        # Sign with HMAC
        signature = hmac.new(
            self.secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        jwt_token = f"{payload_b64}.{signature}"
        return jwt_token

    def decode_token(self, jwt_token: str) -> AuthToken | None:
        """
        Decode JWT token.

        Args:
            jwt_token: JWT string

        Returns:
            Auth token, or None if invalid
        """
        try:
            # Simplified JWT decoding (use PyJWT in production)
            import base64
            import json

            parts = jwt_token.split(".")
            if len(parts) != 2:
                logger.warning("Invalid token format")
                return None

            payload_b64, signature = parts

            # Verify signature
            expected_signature = hmac.new(
                self.secret_key.encode(),
                payload_b64.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Invalid token signature")
                return None

            # Decode payload
            payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
            payload = json.loads(payload_json)

            token = AuthToken(
                user_id=payload["user_id"],
                telegram_id=payload["telegram_id"],
                issued_at=datetime.fromisoformat(payload["issued_at"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
                token_type=payload.get("token_type", "Bearer"),
            )

            # Check expiry
            if token.is_expired():
                logger.warning(f"Token expired for user {token.user_id}")
                return None

            return token

        except Exception as e:
            logger.error(f"Token decode error: {e}")
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
            logger.warning(f"Rate limit exceeded for user {user_id}")
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


__all__ = [
    "AuthService",
    "AuthToken",
    "RateLimitInfo",
]
