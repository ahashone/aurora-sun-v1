"""
Bounded state store with TTL for Aurora Sun V1.

This service provides bounded, persistent state storage with:
- TTL (time-to-live) for automatic expiration
- Maximum size limits to prevent memory exhaustion
- Redis backend for distributed deployments
- In-memory fallback for development

References:
    - F-008: Unbounded in-memory session stores
"""

import asyncio
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from src.services.redis_service import RedisService, get_redis_service


@dataclass
class StateEntry:
    """A state entry with TTL."""
    value: Any
    created_at: float
    accessed_at: float  # For LRU eviction
    ttl: int  # seconds


class BoundedStateStore:
    """
    Bounded state store with TTL and Redis backend.

    Prevents memory exhaustion by:
    - TTL-based expiration (auto-cleanup)
    - Maximum size limit
    - LRU eviction when full (by access time, not creation time)
    - Redis persistence with in-memory fallback
    """

    # Default configuration
    DEFAULT_TTL = 3600  # 1 hour
    MAX_SIZE = 10000  # Maximum entries

    def __init__(
        self,
        max_size: int = MAX_SIZE,
        default_ttl: int = DEFAULT_TTL,
        redis_service: RedisService | None = None,
    ):
        """
        Initialize bounded state store.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default time-to-live in seconds
            redis_service: Redis service instance (uses singleton if None)
        """
        # In-memory store (OrderedDict for LRU)
        self._store: OrderedDict[str, StateEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

        # Redis backend
        self._redis = redis_service or get_redis_service()

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a value with TTL.

        Args:
            key: Unique key
            value: Value to store
            ttl: Time-to-live in seconds (uses default if None)

        Returns:
            True if set successfully, False if full
        """
        async with self._lock:
            effective_ttl = ttl or self._default_ttl
            now = time.time()

            # Try Redis first
            redis_key = f"state_store:{key}"
            entry_dict = {
                "value": value,
                "created_at": now,
                "accessed_at": now,
                "ttl": effective_ttl,
            }

            await self._redis.set(
                redis_key,
                entry_dict,
                ttl=effective_ttl,
            )

            # Always update in-memory store (fallback + cache)
            # Evict expired entries
            self._cleanup_expired()

            # Check size limit
            if len(self._store) >= self._max_size and key not in self._store:
                # Try to evict least recently used entry
                self._evict_lru()
                if len(self._store) >= self._max_size:
                    return False

            # Store value
            entry = StateEntry(
                value=value,
                created_at=now,
                accessed_at=now,
                ttl=effective_ttl,
            )

            # If key exists, remove it first (to update order)
            if key in self._store:
                del self._store[key]

            # Add to end (most recently used)
            self._store[key] = entry

            return True

    async def get(self, key: str) -> Any | None:
        """
        Get a value if it exists and is not expired.

        Args:
            key: Unique key

        Returns:
            Value if found and not expired, None otherwise
        """
        async with self._lock:
            now = time.time()

            # Try in-memory first
            entry = self._store.get(key)

            if entry is not None:
                # Check expiration
                if now - entry.created_at > entry.ttl:
                    del self._store[key]
                    # Also delete from Redis
                    await self._redis.delete(f"state_store:{key}")
                    return None

                # Update access time and move to end (most recently used)
                entry.accessed_at = now
                self._store.move_to_end(key)
                return entry.value

            # Try Redis fallback
            redis_key = f"state_store:{key}"
            redis_value = await self._redis.get(redis_key)

            if redis_value is not None:
                try:
                    entry_dict = json.loads(redis_value)

                    # Check expiration
                    if now - entry_dict["created_at"] > entry_dict["ttl"]:
                        await self._redis.delete(redis_key)
                        return None

                    # Restore to in-memory cache
                    entry = StateEntry(
                        value=entry_dict["value"],
                        created_at=entry_dict["created_at"],
                        accessed_at=now,  # Update access time
                        ttl=entry_dict["ttl"],
                    )

                    # Evict if needed
                    if len(self._store) >= self._max_size:
                        self._evict_lru()

                    # Add to cache (most recently used)
                    self._store[key] = entry

                    return entry_dict["value"]
                except (json.JSONDecodeError, KeyError):
                    # Corrupted entry, delete it
                    await self._redis.delete(redis_key)
                    return None

            return None

    async def delete(self, key: str) -> bool:
        """
        Delete a key.

        Args:
            key: Unique key

        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            # Delete from both stores
            in_memory_deleted = False
            if key in self._store:
                del self._store[key]
                in_memory_deleted = True

            redis_deleted = await self._redis.delete(f"state_store:{key}")

            return in_memory_deleted or redis_deleted

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return await self.get(key) is not None

    def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        expired = [
            key for key, entry in self._store.items()
            if now - entry.created_at > entry.ttl
        ]
        for key in expired:
            del self._store[key]

    def _evict_lru(self) -> bool:
        """Evict the least recently used entry."""
        if not self._store:
            return False

        # OrderedDict: first item is least recently used
        # (because we move_to_end on access)
        lru_key = next(iter(self._store))
        del self._store[lru_key]
        return True

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            # Clear in-memory
            keys_to_delete = list(self._store.keys())
            self._store.clear()

            # Clear Redis (only keys we know about)
            for key in keys_to_delete:
                await self._redis.delete(f"state_store:{key}")

    async def size(self) -> int:
        """Get current number of entries."""
        async with self._lock:
            self._cleanup_expired()
            return len(self._store)


# Global instance
_state_store: BoundedStateStore | None = None
_state_store_lock = asyncio.Lock()


async def get_state_store() -> BoundedStateStore:
    """Get the global state store singleton."""
    global _state_store

    # Double-checked locking pattern for async
    if _state_store is None:
        async with _state_store_lock:
            if _state_store is None:
                _state_store = BoundedStateStore()

    return _state_store
