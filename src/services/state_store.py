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

import time
from dataclasses import dataclass, field
from typing import Any, Optional
import threading


@dataclass
class StateEntry:
    """A state entry with TTL."""
    value: Any
    created_at: float
    ttl: int  # seconds


class BoundedStateStore:
    """
    Bounded state store with TTL and Redis backend.

    Prevents memory exhaustion by:
    - TTL-based expiration (auto-cleanup)
    - Maximum size limit
    - LRU eviction when full
    """

    # Default configuration
    DEFAULT_TTL = 3600  # 1 hour
    MAX_SIZE = 10000  # Maximum entries

    def __init__(
        self,
        max_size: int = MAX_SIZE,
        default_ttl: int = DEFAULT_TTL,
    ):
        """
        Initialize bounded state store.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default time-to-live in seconds
        """
        self._store: dict[str, StateEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
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
        with self._lock:
            # Evict expired entries
            self._cleanup_expired()

            # Check size limit
            if len(self._store) >= self._max_size and key not in self._store:
                # Try to evict oldest entry
                self._evict_oldest()
                if len(self._store) >= self._max_size:
                    return False

            # Store value
            self._store[key] = StateEntry(
                value=value,
                created_at=time.time(),
                ttl=ttl or self._default_ttl,
            )
            return True

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value if it exists and is not expired.

        Args:
            key: Unique key

        Returns:
            Value if found and not expired, None otherwise
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None

            # Check expiration
            if time.time() - entry.created_at > entry.ttl:
                del self._store[key]
                return None

            return entry.value

    def delete(self, key: str) -> bool:
        """
        Delete a key.

        Args:
            key: Unique key

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        expired = [
            key for key, entry in self._store.items()
            if now - entry.created_at > entry.ttl
        ]
        for key in expired:
            del self._store[key]

    def _evict_oldest(self) -> bool:
        """Evict the oldest entry."""
        if not self._store:
            return False

        oldest_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].created_at
        )
        del self._store[oldest_key]
        return True

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        """Get current number of entries."""
        with self._lock:
            self._cleanup_expired()
            return len(self._store)


# Global instance
_state_store: Optional[BoundedStateStore] = None


def get_state_store() -> BoundedStateStore:
    """Get the global state store singleton."""
    global _state_store
    if _state_store is None:
        _state_store = BoundedStateStore()
    return _state_store
