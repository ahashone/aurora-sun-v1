"""Redis service for distributed state management."""

import json
import os
from typing import Any

import redis.asyncio as redis


class RedisService:
    """Redis service for distributed caching and state management."""

    def __init__(self) -> None:
        """Initialize Redis connection."""
        self._client: redis.Redis | None = None
        self._sync_client: redis.Redis | None = None

    async def _ensure_async_client(self) -> redis.Redis | None:
        """Get or create async Redis client."""
        if self._client is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                self._client = redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
                # Test connection
                await self._client.ping()  # type: ignore[misc]
            except redis.ConnectionError:
                # Fall back to None - will use in-memory fallback
                self._client = None
        return self._client

    def _get_sync_client(self) -> redis.Redis | None:
        """Get synchronous Redis client for sync operations."""
        if self._sync_client is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                import redis as sync_redis
                self._sync_client = sync_redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
                self._sync_client.ping()
            except Exception:
                self._sync_client = None
        return self._sync_client

    @property
    def client(self) -> redis.Redis | None:
        """Get the raw async Redis client for advanced operations."""
        return self._client

    async def get(self, key: str) -> str | None:
        """Get value by key."""
        client = await self._ensure_async_client()
        if client is None:
            return None
        result = await client.get(key)
        return str(result) if result is not None else None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set key-value with optional TTL (seconds)."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        if ttl:
            result = await client.setex(key, ttl, json.dumps(value))
            return bool(result)
        result = await client.set(key, json.dumps(value))
        return bool(result)

    async def delete(self, key: str) -> bool:
        """Delete key."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        return bool(await client.delete(key))

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        return bool(await client.exists(key))

    async def incr(self, key: str, amount: int = 1) -> int | None:
        """Increment counter."""
        client = await self._ensure_async_client()
        if client is None:
            return None
        result = await client.incr(key, amount)
        return int(result) if result is not None else None

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on key."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        result = await client.expire(key, ttl)
        return bool(result)

    # Sync versions for backward compatibility
    def get_sync(self, key: str) -> str | None:
        """Get value by key (sync)."""
        client = self._get_sync_client()
        if client is None:
            return None
        result = client.get(key)
        return str(result) if result is not None else None

    def set_sync(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set key-value with optional TTL (seconds, sync)."""
        client = self._get_sync_client()
        if client is None:
            return False
        if ttl:
            result = client.setex(key, ttl, json.dumps(value))
            return bool(result)
        result = client.set(key, json.dumps(value))
        return bool(result)


# Singleton instance
_redis_service: RedisService | None = None


def get_redis_service() -> RedisService:
    """Get Redis service singleton."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service


async def get_redis_client() -> redis.Redis | None:
    """
    Get raw async Redis client for advanced operations (e.g., RateLimiter).

    Returns the underlying redis client or None if unavailable.
    Use this for operations that require direct client access (pipelines,
    sorted sets, etc.). For simple get/set operations, use RedisService directly.
    """
    service = get_redis_service()
    return await service._ensure_async_client()
