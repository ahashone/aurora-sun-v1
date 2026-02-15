"""
Tests for BoundedStateStore.

Covers:
- Set/get/delete operations
- TTL expiration
- LRU eviction
- Size limits
- Redis persistence (mocked)
- Dataclass serialization (CRIT-6)
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.services.state_store import BoundedStateStore

# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Create a mock Redis service."""
    redis = Mock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=True)
    return redis


@pytest.fixture
async def store(mock_redis):
    """Create a state store with mocked Redis."""
    return BoundedStateStore(
        max_size=10,
        default_ttl=3600,
        redis_service=mock_redis,
    )


# =============================================================================
# Basic Operations Tests
# =============================================================================


@pytest.mark.asyncio
async def test_set_and_get(store):
    """Test basic set and get operations."""
    result = await store.set("key1", "value1")
    assert result is True

    value = await store.get("key1")
    assert value == "value1"


@pytest.mark.asyncio
async def test_get_nonexistent_key(store):
    """Test getting a key that doesn't exist."""
    value = await store.get("nonexistent")
    assert value is None


@pytest.mark.asyncio
async def test_set_overwrites_existing(store):
    """Test that set overwrites existing values."""
    await store.set("key1", "value1")
    await store.set("key1", "value2")

    value = await store.get("key1")
    assert value == "value2"


@pytest.mark.asyncio
async def test_delete_key(store):
    """Test deleting a key."""
    await store.set("key1", "value1")
    assert await store.get("key1") == "value1"

    result = await store.delete("key1")
    assert result is True

    assert await store.get("key1") is None


@pytest.mark.asyncio
async def test_delete_nonexistent_key(store):
    """Test deleting a key that doesn't exist."""
    result = await store.delete("nonexistent")
    # Should return False from in-memory, but True from Redis mock
    assert result is True  # Because mock_redis.delete returns True


@pytest.mark.asyncio
async def test_exists(store):
    """Test exists method."""
    assert await store.exists("key1") is False

    await store.set("key1", "value1")
    assert await store.exists("key1") is True

    await store.delete("key1")
    assert await store.exists("key1") is False


# =============================================================================
# TTL Tests
# =============================================================================


@pytest.mark.asyncio
async def test_set_with_custom_ttl(store):
    """Test setting a value with custom TTL."""
    result = await store.set("key1", "value1", ttl=1)
    assert result is True

    # Should exist immediately
    assert await store.get("key1") == "value1"

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Should be expired
    assert await store.get("key1") is None


@pytest.mark.asyncio
async def test_default_ttl(store):
    """Test that default TTL is used when not specified."""
    await store.set("key1", "value1")

    # Get the entry directly to check TTL
    entry = store._store.get("key1")
    assert entry is not None
    assert entry.ttl == 3600  # default_ttl


@pytest.mark.asyncio
async def test_expired_entry_is_removed(store):
    """Test that expired entries are removed on access."""
    await store.set("key1", "value1", ttl=1)
    await asyncio.sleep(1.1)

    # Access should trigger removal
    await store.get("key1")

    # Entry should not be in store
    assert "key1" not in store._store


# =============================================================================
# Size Limit Tests
# =============================================================================


@pytest.mark.asyncio
async def test_size_limit_enforced():
    """Test that size limit is enforced."""
    small_store = BoundedStateStore(max_size=3, default_ttl=3600)

    # Add 3 items (at limit)
    assert await small_store.set("key1", "value1") is True
    assert await small_store.set("key2", "value2") is True
    assert await small_store.set("key3", "value3") is True

    # Add 4th item - should evict LRU
    assert await small_store.set("key4", "value4") is True

    # key1 should be evicted (least recently used)
    assert await small_store.get("key1") is None
    assert await small_store.get("key4") == "value4"


@pytest.mark.asyncio
async def test_lru_eviction_order():
    """Test that LRU eviction works correctly."""
    small_store = BoundedStateStore(max_size=3, default_ttl=3600)

    # Add 3 items
    await small_store.set("key1", "value1")
    await small_store.set("key2", "value2")
    await small_store.set("key3", "value3")

    # Access key1 (makes it most recently used)
    await small_store.get("key1")

    # Add new item - should evict key2 (now least recently used)
    await small_store.set("key4", "value4")

    assert await small_store.get("key1") == "value1"  # Still there
    assert await small_store.get("key2") is None  # Evicted
    assert await small_store.get("key3") == "value3"  # Still there
    assert await small_store.get("key4") == "value4"  # Newly added


@pytest.mark.asyncio
async def test_size_method(store):
    """Test size method."""
    assert await store.size() == 0

    await store.set("key1", "value1")
    assert await store.size() == 1

    await store.set("key2", "value2")
    await store.set("key3", "value3")
    assert await store.size() == 3

    await store.delete("key2")
    assert await store.size() == 2


# =============================================================================
# Cleanup Tests
# =============================================================================


@pytest.mark.asyncio
async def test_cleanup_expired_entries(store):
    """Test that cleanup removes expired entries."""
    # Add items with short TTL
    await store.set("key1", "value1", ttl=1)
    await store.set("key2", "value2", ttl=1)
    await store.set("key3", "value3", ttl=10)

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Trigger cleanup via size()
    size = await store.size()

    # Only key3 should remain
    assert size == 1
    assert await store.get("key3") == "value3"


@pytest.mark.asyncio
async def test_clear(store):
    """Test clearing all entries."""
    await store.set("key1", "value1")
    await store.set("key2", "value2")
    await store.set("key3", "value3")

    assert await store.size() == 3

    await store.clear()

    assert await store.size() == 0
    assert await store.get("key1") is None


# =============================================================================
# Data Type Tests
# =============================================================================


@pytest.mark.asyncio
async def test_store_different_types(store):
    """Test storing different data types."""
    # String
    await store.set("string", "text")
    assert await store.get("string") == "text"

    # Integer
    await store.set("int", 42)
    assert await store.get("int") == 42

    # Float
    await store.set("float", 3.14)
    assert await store.get("float") == 3.14

    # List
    await store.set("list", [1, 2, 3])
    assert await store.get("list") == [1, 2, 3]

    # Dict
    await store.set("dict", {"key": "value"})
    assert await store.get("dict") == {"key": "value"}

    # Boolean
    await store.set("bool", True)
    assert await store.get("bool") is True


@pytest.mark.asyncio
async def test_store_none_value(store):
    """Test storing None as a value."""
    await store.set("key1", None)
    # Getting None is ambiguous with "not found", so implementation may vary
    # This test documents current behavior


# =============================================================================
# Concurrency Tests
# =============================================================================


@pytest.mark.asyncio
async def test_concurrent_access(store):
    """Test concurrent set/get operations."""
    async def set_value(key, value):
        await store.set(key, value)

    async def get_value(key):
        return await store.get(key)

    # Concurrent sets
    await asyncio.gather(
        set_value("key1", "value1"),
        set_value("key2", "value2"),
        set_value("key3", "value3"),
    )

    # Concurrent gets
    results = await asyncio.gather(
        get_value("key1"),
        get_value("key2"),
        get_value("key3"),
    )

    assert "value1" in results
    assert "value2" in results
    assert "value3" in results


# =============================================================================
# Access Time Tracking Tests
# =============================================================================


@pytest.mark.asyncio
async def test_access_time_updated_on_get(store):
    """Test that access time is updated on get."""
    await store.set("key1", "value1")

    # Get initial entry
    entry1 = store._store.get("key1")
    initial_access_time = entry1.accessed_at

    # Wait a bit
    await asyncio.sleep(0.1)

    # Access again
    await store.get("key1")

    # Access time should be updated
    entry2 = store._store.get("key1")
    assert entry2.accessed_at > initial_access_time


@pytest.mark.asyncio
async def test_move_to_end_on_access(store):
    """Test that accessing a key moves it to end (most recent)."""
    await store.set("key1", "value1")
    await store.set("key2", "value2")
    await store.set("key3", "value3")

    # Access key1 (should move to end)
    await store.get("key1")

    # Check order
    keys = list(store._store.keys())
    assert keys[-1] == "key1"  # key1 is now most recent


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_empty_key(store):
    """Test behavior with empty string key."""
    await store.set("", "empty_key_value")
    assert await store.get("") == "empty_key_value"


@pytest.mark.asyncio
async def test_very_long_key(store):
    """Test behavior with very long key."""
    long_key = "x" * 1000
    await store.set(long_key, "value")
    assert await store.get(long_key) == "value"


@pytest.mark.asyncio
async def test_zero_ttl(store):
    """Test behavior with zero TTL."""
    # TTL=0 is falsy in Python, so `ttl or default_ttl` falls back to default_ttl.
    # This means TTL=0 effectively uses the default TTL (3600s), not instant expiry.
    await store.set("key1", "value1", ttl=0)

    # With TTL=0 falling back to default, the entry should still be accessible
    await asyncio.sleep(0.1)
    assert await store.get("key1") == "value1"


@pytest.mark.asyncio
async def test_negative_ttl(store):
    """Test behavior with negative TTL."""
    # Implementation may handle this differently
    # This test documents current behavior
    await store.set("key1", "value1", ttl=-1)


@pytest.mark.asyncio
async def test_overwrite_updates_ttl(store):
    """Test that overwriting a key updates its TTL."""
    # Set with short TTL
    await store.set("key1", "value1", ttl=1)

    # Overwrite with longer TTL
    await store.set("key1", "value2", ttl=10)

    # Wait past original TTL
    await asyncio.sleep(1.1)

    # Should still exist (new TTL)
    assert await store.get("key1") == "value2"


# =============================================================================
# Dataclass Serialization Tests (CRIT-6)
# =============================================================================


@dataclass
class MockPlanningSession:
    """Mock planning session for testing dataclass serialization."""
    scope: str
    priority_count: int
    created_at: datetime
    tags: set[str]


@dataclass
class MockFutureLetterSession:
    """Mock future letter session for testing dataclass serialization."""
    time_horizon: int
    letter_content: str
    created_at: datetime


@pytest.mark.asyncio
async def test_store_dataclass_instance(store):
    """Test that BoundedStateStore can store dataclass instances (CRIT-6)."""
    session = MockPlanningSession(
        scope="Complete project",
        priority_count=5,
        created_at=datetime(2026, 2, 15, 10, 0, 0),
        tags={"urgent", "work"}
    )

    # Should not raise TypeError when serializing to Redis
    result = await store.set("planning_session", session)
    assert result is True

    # Verify Redis.set was called (which would have triggered JSON encoding)
    store._redis.set.assert_called()

    # Verify it's stored and can be retrieved from in-memory store
    # Note: In-memory retrieval returns the original dataclass
    retrieved = await store.get("planning_session")
    assert retrieved is not None
    assert isinstance(retrieved, MockPlanningSession)
    assert retrieved.scope == "Complete project"
    assert retrieved.priority_count == 5
    assert retrieved.created_at == datetime(2026, 2, 15, 10, 0, 0)
    assert retrieved.tags == {"urgent", "work"}


@pytest.mark.asyncio
async def test_store_nested_dataclass(store):
    """Test storing complex nested dataclass structures."""
    @dataclass
    class OuterSession:
        """Outer session for testing."""
        name: str
        inner: MockPlanningSession

    outer = OuterSession(
        name="test_session",
        inner=MockPlanningSession(
            scope="Inner scope",
            priority_count=3,
            created_at=datetime(2026, 1, 1),
            tags=set()
        )
    )

    # Should not raise TypeError when serializing to Redis
    result = await store.set("nested_session", outer)
    assert result is True

    # Verify Redis.set was called (would have triggered nested serialization)
    store._redis.set.assert_called()

    retrieved = await store.get("nested_session")
    assert retrieved is not None
    assert isinstance(retrieved, OuterSession)
    assert retrieved.name == "test_session"
    assert retrieved.inner.scope == "Inner scope"
    assert retrieved.inner.priority_count == 3


@pytest.mark.asyncio
async def test_store_multiple_session_types(store):
    """Test storing different session types simultaneously."""
    planning = MockPlanningSession(
        scope="Planning test",
        priority_count=1,
        created_at=datetime(2026, 2, 15),
        tags={"test"}
    )

    future_letter = MockFutureLetterSession(
        time_horizon=10,
        letter_content="Dear future self...",
        created_at=datetime(2026, 2, 15, 12, 0, 0)
    )

    # Store both - should not raise TypeError
    await store.set("session:planning:123", planning)
    await store.set("session:future_letter:456", future_letter)

    # Retrieve both
    retrieved_planning = await store.get("session:planning:123")
    retrieved_letter = await store.get("session:future_letter:456")

    assert retrieved_planning is not None
    assert isinstance(retrieved_planning, MockPlanningSession)
    assert retrieved_planning.scope == "Planning test"

    assert retrieved_letter is not None
    assert isinstance(retrieved_letter, MockFutureLetterSession)
    assert retrieved_letter.time_horizon == 10
    assert retrieved_letter.letter_content == "Dear future self..."
