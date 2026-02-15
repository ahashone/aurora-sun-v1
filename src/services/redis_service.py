"""Redis service for distributed state management."""

import dataclasses
import json
import os
from datetime import date, datetime
from enum import Enum
from typing import Any

import redis.asyncio as redis


class AuroraJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for Aurora Sun that handles:
    - dataclasses → dict via dataclasses.asdict()
    - datetime/date → .isoformat()
    - Enum → .value
    - set → list
    - Any other non-serializable → str()

    This encoder is safe and never raises — uses str() as last resort.
    """

    def default(self, obj: Any) -> Any:
        """Convert non-serializable objects to JSON-serializable types."""
        # Handle dataclasses
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)

        # Handle datetime/date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        # Handle Enum
        if isinstance(obj, Enum):
            return obj.value

        # Handle set
        if isinstance(obj, set):
            return list(obj)

        # Last resort: convert to string (never raise)
        try:
            return str(obj)
        except Exception:  # Intentional catch-all: JSON encoder last-resort fallback, must never raise
            return f"<non-serializable: {type(obj).__name__}>"


class RedisService:
    """Redis service for distributed caching and state management."""

    def __init__(self) -> None:
        """Initialize Redis connection."""
        self._client: redis.Redis | None = None
        self._sync_client: redis.Redis | None = None

    @staticmethod
    def _tls_kwargs(redis_url: str) -> dict[str, Any]:
        """Build TLS keyword arguments when using rediss:// URLs."""
        import ssl

        if not redis_url.startswith("rediss://"):
            return {}

        cert_path = os.environ.get("REDIS_TLS_CERT_PATH")
        if cert_path:
            ssl_ctx = ssl.create_default_context(cafile=cert_path)
        else:
            ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        return {"ssl": ssl_ctx}

    async def _ensure_async_client(self) -> redis.Redis | None:
        """Get or create async Redis client."""
        if self._client is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                tls = self._tls_kwargs(redis_url)
                self._client = redis.from_url(  # type: ignore[no-untyped-call]
                    redis_url,
                    decode_responses=True,
                    **tls,
                )
                # Test connection
                await self._client.ping()
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
                tls = self._tls_kwargs(redis_url)
                self._sync_client = sync_redis.from_url(  # type: ignore[no-untyped-call]
                    redis_url,
                    decode_responses=True,
                    **tls,
                )
                self._sync_client.ping()
            except Exception:  # Intentional catch-all: graceful fallback when sync Redis client unavailable
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
            result = await client.setex(key, ttl, json.dumps(value, cls=AuroraJSONEncoder))
            return bool(result)
        result = await client.set(key, json.dumps(value, cls=AuroraJSONEncoder))
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
            result = client.setex(key, ttl, json.dumps(value, cls=AuroraJSONEncoder))
            return bool(result)
        result = client.set(key, json.dumps(value, cls=AuroraJSONEncoder))
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
