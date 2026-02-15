"""
Tests for RedisService.

Covers:
- Basic operations (get, set, delete, exists)
- TTL handling
- Counter operations (incr, expire)
- Connection handling (with mocks)
- Sync vs async methods
- Custom JSON encoder (dataclasses, datetime, etc.)
"""

from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.services.redis_service import AuroraJSONEncoder, RedisService, get_redis_service

# =============================================================================
# Mock Redis Client
# =============================================================================


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value
        return True

    async def setex(self, key, ttl, value):
        self.data[key] = value
        self.ttls[key] = ttl
        return True

    async def delete(self, key):
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    async def exists(self, key):
        return 1 if key in self.data else 0

    async def incr(self, key, amount=1):
        current = int(self.data.get(key, 0))
        self.data[key] = str(current + amount)
        return current + amount

    async def expire(self, key, ttl):
        if key in self.data:
            self.ttls[key] = ttl
            return 1
        return 0

    async def ping(self):
        return True


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    return MockRedisClient()


@pytest.fixture
async def redis_service(mock_redis_client):
    """Create a RedisService with mocked client."""
    service = RedisService()
    service._client = mock_redis_client
    return service


# =============================================================================
# Basic Operations Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_nonexistent_key(redis_service):
    """Test getting a key that doesn't exist."""
    value = await redis_service.get("nonexistent")
    assert value is None


@pytest.mark.asyncio
async def test_set_and_get(redis_service):
    """Test basic set and get operations."""
    result = await redis_service.set("key1", "value1")
    assert result is True

    value = await redis_service.get("key1")
    assert value == '"value1"'  # JSON-encoded


@pytest.mark.asyncio
async def test_set_with_ttl(redis_service):
    """Test setting a value with TTL."""
    result = await redis_service.set("key1", "value1", ttl=60)
    assert result is True

    # Verify TTL was set
    assert "key1" in redis_service._client.ttls
    assert redis_service._client.ttls["key1"] == 60


@pytest.mark.asyncio
async def test_delete_key(redis_service):
    """Test deleting a key."""
    await redis_service.set("key1", "value1")
    assert await redis_service.get("key1") is not None

    result = await redis_service.delete("key1")
    assert result is True

    assert await redis_service.get("key1") is None


@pytest.mark.asyncio
async def test_delete_nonexistent_key(redis_service):
    """Test deleting a key that doesn't exist."""
    result = await redis_service.delete("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_exists(redis_service):
    """Test exists method."""
    assert await redis_service.exists("key1") is False

    await redis_service.set("key1", "value1")
    assert await redis_service.exists("key1") is True

    await redis_service.delete("key1")
    assert await redis_service.exists("key1") is False


# =============================================================================
# Counter Operations Tests
# =============================================================================


@pytest.mark.asyncio
async def test_incr_new_key(redis_service):
    """Test incrementing a new key."""
    result = await redis_service.incr("counter")
    assert result == 1


@pytest.mark.asyncio
async def test_incr_existing_key(redis_service):
    """Test incrementing an existing key."""
    await redis_service.incr("counter")
    result = await redis_service.incr("counter")
    assert result == 2


@pytest.mark.asyncio
async def test_incr_with_amount(redis_service):
    """Test incrementing with custom amount."""
    await redis_service.incr("counter")
    result = await redis_service.incr("counter", amount=5)
    assert result == 6


@pytest.mark.asyncio
async def test_expire_existing_key(redis_service):
    """Test setting expiration on existing key."""
    await redis_service.set("key1", "value1")
    result = await redis_service.expire("key1", 120)
    assert result is True

    assert redis_service._client.ttls.get("key1") == 120


@pytest.mark.asyncio
async def test_expire_nonexistent_key(redis_service):
    """Test setting expiration on non-existent key."""
    result = await redis_service.expire("nonexistent", 120)
    assert result is False


# =============================================================================
# Data Type Tests
# =============================================================================


@pytest.mark.asyncio
async def test_set_different_types(redis_service):
    """Test storing different data types (all JSON-encoded)."""
    # String
    await redis_service.set("string", "text")
    assert await redis_service.get("string") == '"text"'

    # Integer
    await redis_service.set("int", 42)
    assert await redis_service.get("int") == '42'

    # Dict
    await redis_service.set("dict", {"key": "value"})
    value = await redis_service.get("dict")
    assert '{"key": "value"}' in value or '{"key":"value"}' in value


# =============================================================================
# Connection Tests (with real mocks)
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_async_client_creates_client():
    """Test that _ensure_async_client creates a client."""
    with patch('src.services.redis_service.redis.from_url') as mock_from_url:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_from_url.return_value = mock_client

        service = RedisService()
        client = await service._ensure_async_client()

        assert client is not None
        assert client == mock_client
        mock_client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_async_client_handles_connection_error():
    """Test that connection errors are handled gracefully."""
    import redis as redis_lib

    with patch('src.services.redis_service.redis.from_url') as mock_from_url:
        mock_client = AsyncMock()
        # Production code catches redis.ConnectionError, not generic Exception
        mock_client.ping = AsyncMock(side_effect=redis_lib.ConnectionError("Connection failed"))
        mock_from_url.return_value = mock_client

        service = RedisService()
        client = await service._ensure_async_client()

        # Should return None on connection failure
        assert client is None


@pytest.mark.asyncio
async def test_operations_with_no_client():
    """Test that operations handle missing client gracefully."""
    service = RedisService()
    service._client = None

    # Mock _ensure_async_client to return None
    service._ensure_async_client = AsyncMock(return_value=None)

    # All operations should handle this gracefully
    assert await service.get("key") is None
    assert await service.set("key", "value") is False
    assert await service.delete("key") is False
    assert await service.exists("key") is False
    assert await service.incr("key") is None
    assert await service.expire("key", 60) is False


# =============================================================================
# Singleton Tests
# =============================================================================


def test_get_redis_service_singleton():
    """Test that get_redis_service returns a singleton."""
    service1 = get_redis_service()
    service2 = get_redis_service()

    assert service1 is service2


# =============================================================================
# TLS Tests
# =============================================================================


def test_tls_kwargs_with_rediss_url():
    """Test TLS kwargs generation for rediss:// URLs."""
    kwargs = RedisService._tls_kwargs("rediss://localhost:6379")

    assert "ssl" in kwargs
    assert kwargs["ssl"] is not None


def test_tls_kwargs_with_redis_url():
    """Test TLS kwargs for regular redis:// URLs."""
    kwargs = RedisService._tls_kwargs("redis://localhost:6379")

    assert kwargs == {}


@patch.dict('os.environ', {'REDIS_TLS_CERT_PATH': '/path/to/cert.pem'})
def test_tls_kwargs_with_cert_path():
    """Test TLS kwargs with custom cert path."""
    with patch('ssl.create_default_context') as mock_ssl:
        mock_context = MagicMock()
        mock_ssl.return_value = mock_context

        kwargs = RedisService._tls_kwargs("rediss://localhost:6379")

        assert "ssl" in kwargs
        mock_ssl.assert_called_once_with(cafile='/path/to/cert.pem')


# =============================================================================
# Client Property Tests
# =============================================================================


def test_client_property():
    """Test accessing the client property."""
    service = RedisService()
    mock_client = Mock()
    service._client = mock_client

    assert service.client == mock_client


# =============================================================================
# Sync Methods Tests (backward compatibility)
# =============================================================================


def test_get_sync_client_creates_client():
    """Test that _get_sync_client creates a sync client."""
    # redis is imported locally inside _get_sync_client as 'import redis as sync_redis'
    with patch('redis.from_url') as mock_from_url:
        mock_client = Mock()
        mock_client.ping = Mock(return_value=True)
        mock_from_url.return_value = mock_client

        service = RedisService()
        client = service._get_sync_client()

        assert client is not None
        assert client == mock_client
        mock_client.ping.assert_called_once()


def test_get_sync_handles_error():
    """Test that sync client creation handles errors."""
    with patch('redis.from_url') as mock_from_url:
        mock_from_url.side_effect = Exception("Connection failed")

        service = RedisService()
        client = service._get_sync_client()

        assert client is None


def test_get_sync_method():
    """Test get_sync method."""
    service = RedisService()
    mock_client = Mock()
    mock_client.get = Mock(return_value="value")
    service._sync_client = mock_client

    result = service.get_sync("key")

    assert result == "value"
    mock_client.get.assert_called_once_with("key")


def test_get_sync_with_no_client():
    """Test get_sync with no client."""
    service = RedisService()
    service._sync_client = None
    service._get_sync_client = Mock(return_value=None)

    result = service.get_sync("key")

    assert result is None


def test_set_sync_method():
    """Test set_sync method."""
    service = RedisService()
    mock_client = Mock()
    mock_client.set = Mock(return_value=True)
    service._sync_client = mock_client

    result = service.set_sync("key", "value")

    assert result is True


def test_set_sync_with_ttl():
    """Test set_sync with TTL."""
    service = RedisService()
    mock_client = Mock()
    mock_client.setex = Mock(return_value=True)
    service._sync_client = mock_client

    result = service.set_sync("key", "value", ttl=60)

    assert result is True
    mock_client.setex.assert_called_once()


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_empty_key(redis_service):
    """Test behavior with empty string key."""
    await redis_service.set("", "value")
    assert await redis_service.get("") == '"value"'


@pytest.mark.asyncio
async def test_very_long_key(redis_service):
    """Test behavior with very long key."""
    long_key = "x" * 1000
    await redis_service.set(long_key, "value")
    assert await redis_service.get(long_key) == '"value"'


@pytest.mark.asyncio
async def test_special_characters_in_key(redis_service):
    """Test keys with special characters."""
    special_keys = [
        "key:with:colons",
        "key/with/slashes",
        "key.with.dots",
        "key-with-dashes",
        "key_with_underscores",
    ]

    for key in special_keys:
        await redis_service.set(key, f"value_{key}")
        assert await redis_service.get(key) == f'"value_{key}"'


# =============================================================================
# Custom JSON Encoder Tests (CRIT-6)
# =============================================================================


@dataclass
class TestSession:
    """Test dataclass for encoder testing."""
    name: str
    count: int
    created_at: datetime
    tags: set[str]


class TestStatus(Enum):
    """Test enum for encoder testing."""
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"


@pytest.mark.asyncio
async def test_encoder_handles_dataclass(redis_service):
    """Test that custom encoder handles dataclass instances."""
    session = TestSession(
        name="test_session",
        count=42,
        created_at=datetime(2026, 2, 15, 10, 30, 0),
        tags={"tag1", "tag2"}
    )

    # Should not raise TypeError
    result = await redis_service.set("session_key", session)
    assert result is True

    # Verify it was stored correctly (as JSON string)
    stored_value = await redis_service.get("session_key")
    assert stored_value is not None
    assert "test_session" in stored_value
    assert "42" in stored_value
    assert "2026-02-15T10:30:00" in stored_value
    # Set is converted to list
    assert "tag1" in stored_value and "tag2" in stored_value


@pytest.mark.asyncio
async def test_encoder_handles_datetime_objects(redis_service):
    """Test that custom encoder handles datetime and date objects."""
    test_data = {
        "timestamp": datetime(2026, 2, 15, 14, 30, 45),
        "date_only": date(2026, 2, 15),
        "name": "test"
    }

    result = await redis_service.set("datetime_key", test_data)
    assert result is True

    stored_value = await redis_service.get("datetime_key")
    assert stored_value is not None
    assert "2026-02-15T14:30:45" in stored_value  # datetime.isoformat()
    assert "2026-02-15" in stored_value  # date.isoformat()


@pytest.mark.asyncio
async def test_encoder_handles_enum_objects(redis_service):
    """Test that custom encoder handles Enum objects."""
    test_data = {
        "status": TestStatus.ACTIVE,
        "description": "test"
    }

    result = await redis_service.set("enum_key", test_data)
    assert result is True

    stored_value = await redis_service.get("enum_key")
    assert stored_value is not None
    assert "active" in stored_value  # Enum.value


@pytest.mark.asyncio
async def test_encoder_handles_set_objects(redis_service):
    """Test that custom encoder handles set objects."""
    test_data = {
        "tags": {"python", "redis", "testing"},
        "name": "test"
    }

    result = await redis_service.set("set_key", test_data)
    assert result is True

    stored_value = await redis_service.get("set_key")
    assert stored_value is not None
    # Set is converted to list (order may vary)
    assert "python" in stored_value
    assert "redis" in stored_value
    assert "testing" in stored_value


@pytest.mark.asyncio
async def test_encoder_handles_nested_dataclass(redis_service):
    """Test that custom encoder handles nested dataclass instances."""
    @dataclass
    class NestedSession:
        """Nested dataclass for testing."""
        outer_name: str
        inner_session: TestSession

    nested = NestedSession(
        outer_name="outer",
        inner_session=TestSession(
            name="inner",
            count=99,
            created_at=datetime(2026, 1, 1),
            tags=set()
        )
    )

    result = await redis_service.set("nested_key", nested)
    assert result is True

    stored_value = await redis_service.get("nested_key")
    assert stored_value is not None
    assert "outer" in stored_value
    assert "inner" in stored_value
    assert "99" in stored_value


@pytest.mark.asyncio
async def test_encoder_never_raises(redis_service):
    """Test that encoder never raises exceptions (safe fallback)."""
    # Test with a non-serializable object
    class CustomClass:
        def __init__(self):
            self.value = "test"

    test_data = {
        "custom": CustomClass(),
        "name": "test"
    }

    # Should not raise, should convert to string
    result = await redis_service.set("custom_key", test_data)
    assert result is True

    stored_value = await redis_service.get("custom_key")
    assert stored_value is not None
