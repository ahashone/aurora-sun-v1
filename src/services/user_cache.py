"""
Redis cache for user lookups (PERF-002).

Every Telegram webhook hit queries PostgreSQL for the user record.
This module adds a Redis caching layer to avoid repeated DB queries
for the same user within a short time window.

Cache strategy:
    - Key format: user:hash:{telegram_id_hash}
    - TTL: 300 seconds (5 minutes)
    - Cached fields: id, telegram_id, language, timezone, working_style_code,
      processing_restriction, letta_agent_id
    - NOT cached: name (encrypted, must always come from DB)
    - Invalidation: on user update (explicit call to invalidate_user_cache)

Data Classification: INTERNAL (only non-sensitive fields cached)

References:
    - ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

import json
import logging
from typing import Any

from src.services.redis_service import RedisService, get_redis_service

logger = logging.getLogger(__name__)

# Cache configuration
USER_CACHE_PREFIX = "user:hash:"
USER_CACHE_TTL = 300  # 5 minutes

# Fields safe to cache (no encrypted/PII fields)
CACHEABLE_FIELDS = (
    "id",
    "telegram_id",
    "language",
    "timezone",
    "working_style_code",
    "processing_restriction",
    "letta_agent_id",
)


def _cache_key(telegram_id_hash: str) -> str:
    """Build the Redis cache key for a user lookup.

    Args:
        telegram_id_hash: HMAC-SHA256 hashed Telegram ID

    Returns:
        Redis key string
    """
    return f"{USER_CACHE_PREFIX}{telegram_id_hash}"


def user_to_cache_dict(user: Any) -> dict[str, Any]:
    """Extract cacheable fields from a User ORM object.

    Only non-sensitive fields are included. Encrypted fields (name)
    are deliberately excluded.

    Args:
        user: User ORM instance

    Returns:
        Dict of cacheable field values
    """
    return {
        field: getattr(user, field, None)
        for field in CACHEABLE_FIELDS
    }


async def get_cached_user(
    telegram_id_hash: str,
    redis_service: RedisService | None = None,
) -> dict[str, Any] | None:
    """Retrieve a cached user dict from Redis.

    Args:
        telegram_id_hash: HMAC-SHA256 hashed Telegram ID
        redis_service: Optional RedisService instance (uses singleton if None)

    Returns:
        Dict of cached user fields, or None if not cached / Redis unavailable
    """
    svc = redis_service or get_redis_service()
    key = _cache_key(telegram_id_hash)
    try:
        raw = await svc.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        if isinstance(data, dict) and "id" in data:
            return data
        logger.warning("Invalid user cache data for key %s", key)
        return None
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to deserialize user cache for %s: %s", key, exc)
        return None
    except Exception as exc:  # Intentional catch-all: cache miss is acceptable, never block on cache errors
        logger.warning("Unexpected error reading user cache: %s", exc)
        return None


async def set_cached_user(
    telegram_id_hash: str,
    user: Any,
    redis_service: RedisService | None = None,
    ttl: int = USER_CACHE_TTL,
) -> bool:
    """Cache a user record in Redis.

    Only non-sensitive fields are stored. Encrypted fields are excluded.

    Args:
        telegram_id_hash: HMAC-SHA256 hashed Telegram ID
        user: User ORM instance
        redis_service: Optional RedisService instance (uses singleton if None)
        ttl: Cache TTL in seconds (default 300)

    Returns:
        True if successfully cached, False otherwise
    """
    svc = redis_service or get_redis_service()
    key = _cache_key(telegram_id_hash)
    try:
        data = user_to_cache_dict(user)
        return await svc.set(key, data, ttl=ttl)
    except Exception as exc:  # Intentional catch-all: cache write failure is non-critical
        logger.warning("Failed to cache user for %s: %s", key, exc)
        return False


async def invalidate_user_cache(
    telegram_id_hash: str,
    redis_service: RedisService | None = None,
) -> bool:
    """Invalidate (delete) a cached user record.

    Call this whenever a user record is updated in the database.

    Args:
        telegram_id_hash: HMAC-SHA256 hashed Telegram ID
        redis_service: Optional RedisService instance (uses singleton if None)

    Returns:
        True if successfully deleted, False otherwise
    """
    svc = redis_service or get_redis_service()
    key = _cache_key(telegram_id_hash)
    try:
        return await svc.delete(key)
    except Exception as exc:  # Intentional catch-all: cache invalidation failure is non-critical
        logger.warning("Failed to invalidate user cache for %s: %s", key, exc)
        return False


__all__ = [
    "USER_CACHE_PREFIX",
    "USER_CACHE_TTL",
    "CACHEABLE_FIELDS",
    "get_cached_user",
    "set_cached_user",
    "invalidate_user_cache",
    "user_to_cache_dict",
]
