"""
Authentication and Authorization for Aurora Sun V1 REST API.

Implements:
- JWT token-based authentication (via PyJWT)
- JWT token revocation via Redis blacklist (jti-based)
- User identification via token
- Rate limiting
- Request verification
- Startup secrets validation (fail-fast if missing)

Reference: ROADMAP 5.4, ARCHITECTURE.md Section 14 (SW-14: REST API)
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt

from src.lib.security import SecurityEventLogger, hash_uid

logger = logging.getLogger(__name__)


@dataclass
class AuthToken:
    """
    JWT authentication token.

    Contains user identification, expiry information, and a unique
    JWT ID (jti) used for token revocation via Redis blacklist.
    """

    user_id: int
    telegram_id: int
    issued_at: datetime
    expires_at: datetime
    token_type: str = "Bearer"
    jti: str = field(default_factory=lambda: str(uuid.uuid4()))

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
            "jti": self.jti,
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

        Includes jti (JWT ID) claim for token revocation support.

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
            "jti": token.jti,
            "iss": "aurora-sun",
            "aud": "aurora-sun-api",
        }
        return pyjwt.encode(payload, self.secret_key, algorithm="HS256")

    def decode_token(self, jwt_token: str) -> AuthToken | None:
        """
        Decode JWT token using PyJWT.

        Checks the Redis revocation blacklist if a TokenBlacklist is configured.
        Returns None for revoked tokens.

        Args:
            jwt_token: JWT string

        Returns:
            Auth token, or None if invalid or revoked
        """
        try:
            payload = pyjwt.decode(
                jwt_token,
                self.secret_key,
                algorithms=["HS256"],
                audience="aurora-sun-api",
                issuer="aurora-sun",
            )

            jti = payload.get("jti", "")

            token = AuthToken(
                user_id=int(payload["sub"]),
                telegram_id=payload["telegram_id"],
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                token_type=payload.get("type", "Bearer"),
                jti=jti,
            )

            # Check revocation blacklist (sync check for use in non-async contexts)
            blacklist = get_token_blacklist()
            if blacklist.is_token_revoked_sync(jti):
                logger.warning("Token revoked: jti=%s", jti)
                SecurityEventLogger.auth_failure("token_revoked", detail=f"jti={jti}")
                return None

            return token

        except pyjwt.ExpiredSignatureError:
            logger.warning("Token expired")
            SecurityEventLogger.auth_failure("token_expired")
            return None
        except pyjwt.InvalidTokenError as e:
            logger.error("Token decode error: %s", e)
            SecurityEventLogger.auth_failure("invalid_token", detail=str(e))
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


class TokenBlacklist:
    """
    JWT token revocation via Redis blacklist.

    Stores revoked token JTIs (JWT IDs) in Redis with auto-expiry matching
    the original token's expiration. This ensures blacklist entries are
    automatically cleaned up when the token would have expired anyway.

    Redis key format: ``aurora:token:blacklist:{jti}``

    When Redis is unavailable, falls back to an in-memory set (bounded to
    prevent unbounded growth). The in-memory fallback is NOT shared across
    processes, so it is only suitable for development / single-process mode.
    """

    REDIS_KEY_PREFIX = "aurora:token:blacklist:"

    # Maximum in-memory blacklist entries (memory safety for fallback mode)
    MAX_MEMORY_ENTRIES = 10000

    def __init__(self) -> None:
        """Initialize token blacklist."""
        self._memory_blacklist: set[str] = set()

    def _get_redis_service(self) -> Any:
        """
        Get the Redis service singleton (lazy import to avoid circular deps).

        Returns:
            RedisService instance
        """
        from src.services.redis_service import get_redis_service

        return get_redis_service()

    async def revoke_token(self, jti: str, expires_at: datetime) -> bool:
        """
        Add a token JTI to the revocation blacklist.

        The Redis entry auto-expires when the original token would have expired,
        so the blacklist is self-cleaning.

        Args:
            jti: JWT ID to revoke
            expires_at: When the original token expires (for TTL calculation)

        Returns:
            True if successfully blacklisted, False if Redis unavailable
            (falls back to in-memory)
        """
        if not jti:
            return False

        # Calculate TTL: seconds until the token would naturally expire
        ttl_seconds = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)

        redis_svc = self._get_redis_service()
        key = f"{self.REDIS_KEY_PREFIX}{jti}"
        result = await redis_svc.set(key, "revoked", ttl=ttl_seconds)

        if result:
            logger.info("Token revoked via Redis: jti=%s, ttl=%ds", jti, ttl_seconds)
            return True

        # Fallback to in-memory if Redis is unavailable
        self._add_to_memory_blacklist(jti)
        logger.warning(
            "Redis unavailable, token revoked in-memory only: jti=%s", jti
        )
        return False

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token JTI is in the revocation blacklist (async).

        Args:
            jti: JWT ID to check

        Returns:
            True if the token is revoked
        """
        if not jti:
            return False

        # Check in-memory blacklist first (fast path)
        if jti in self._memory_blacklist:
            return True

        # Check Redis
        redis_svc = self._get_redis_service()
        result = await redis_svc.exists(f"{self.REDIS_KEY_PREFIX}{jti}")
        return bool(result)

    def is_token_revoked_sync(self, jti: str) -> bool:
        """
        Check if a token JTI is in the revocation blacklist (sync).

        Uses the sync Redis client for non-async contexts (e.g., decode_token).
        Falls back to in-memory blacklist only if Redis is unavailable.

        Args:
            jti: JWT ID to check

        Returns:
            True if the token is revoked
        """
        if not jti:
            return False

        # Check in-memory blacklist first (fast path)
        if jti in self._memory_blacklist:
            return True

        # Check Redis via sync client
        redis_svc = self._get_redis_service()
        sync_client = redis_svc._get_sync_client()
        if sync_client is not None:
            try:
                result = sync_client.exists(f"{self.REDIS_KEY_PREFIX}{jti}")
                return bool(result)
            except (OSError, ConnectionError, TimeoutError):
                logger.debug("Redis sync check failed for jti=%s, using memory only", jti)

        return False

    def _add_to_memory_blacklist(self, jti: str) -> None:
        """
        Add JTI to in-memory blacklist with size bound.

        If the blacklist exceeds MAX_MEMORY_ENTRIES, the oldest half is cleared.
        This is a simple eviction strategy since set doesn't preserve order,
        but it prevents unbounded memory growth.
        """
        if len(self._memory_blacklist) >= self.MAX_MEMORY_ENTRIES:
            # Clear oldest half (set doesn't preserve order, so this is approximate)
            entries = list(self._memory_blacklist)
            self._memory_blacklist = set(entries[len(entries) // 2 :])
            logger.info(
                "In-memory blacklist eviction: %d -> %d entries",
                len(entries),
                len(self._memory_blacklist),
            )
        self._memory_blacklist.add(jti)


# Singleton for TokenBlacklist
_token_blacklist: TokenBlacklist | None = None


def get_token_blacklist() -> TokenBlacklist:
    """Get or create the TokenBlacklist singleton."""
    global _token_blacklist
    if _token_blacklist is None:
        _token_blacklist = TokenBlacklist()
    return _token_blacklist


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
    "TokenBlacklist",
    "get_token_blacklist",
    "validate_secrets",
]
