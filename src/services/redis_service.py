"""Redis service for distributed state management."""

import os
from typing import Any, Optional
import json

import redis.asyncio as redis


class RedisService:
    """Redis service for distributed caching and state management."""

    def __init__(self):
        """Initialize Redis connection."""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._client: Optional[redis.Redis] = None
        self._sync_client: Optional[redis.Redis] = None

    async def _ensure_async_client(self) -> Optional[redis.Redis]:
        """Get or create async Redis client."""
        if self._client is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                self._client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                await self._client.ping()
            except redis.ConnectionError:
                # Fall back to None - will use in-memory fallback
                self._client = None
        return self._client

    def _get_sync_client(self) -> Optional[redis.Redis]:
        """Get synchronous Redis client for sync operations."""
        if self._sync_client is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                import redis as sync_redis
                self._sync_client = sync_redis.from_url(redis_url, decode_responses=True)
                self._sync_client.ping()
            except Exception:
                self._sync_client = None
        return self._sync_client

    @property
    def client(self):
        """Get the raw async Redis client for advanced operations."""
        return self._client

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        client = await self._ensure_async_client()
        if client is None:
            return None
        return await client.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value with optional TTL (seconds)."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        if ttl:
            return await client.setex(key, ttl, json.dumps(value))
        return await client.set(key, json.dumps(value))

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

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter."""
        client = await self._ensure_async_client()
        if client is None:
            return None
        return await client.incr(key, amount)

    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on key."""
        client = await self._ensure_async_client()
        if client is None:
            return False
        return await client.expire(key, ttl)

    # Sync versions for backward compatibility
    def get_sync(self, key: str) -> Optional[str]:
        """Get value by key (sync)."""
        client = self._get_sync_client()
        if client is None:
            return None
        return client.get(key)

    def set_sync(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value with optional TTL (seconds, sync)."""
        client = self._get_sync_client()
        if client is None:
            return False
        if ttl:
            return client.setex(key, ttl, json.dumps(value))
        return client.set(key, json.dumps(value))


# Singleton instance
_redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    """Get Redis service singleton."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service


async def get_redis_client():
    """
    Get raw async Redis client for advanced operations (e.g., RateLimiter).

    Returns the underlying redis client or None if unavailable.
    Use this for operations that require direct client access (pipelines,
    sorted sets, etc.). For simple get/set operations, use RedisService directly.
    """
    service = get_redis_service()
    return await service._ensure_async_client()
