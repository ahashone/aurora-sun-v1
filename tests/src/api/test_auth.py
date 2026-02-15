"""
Tests for API Authentication (src/api/auth.py).

Tests:
- Token generation
- Token encoding/decoding
- Token validation
- Token revocation (Redis blacklist)
- Rate limiting
- Request authentication
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.auth import AuthService, AuthToken, TokenBlacklist, get_token_blacklist


class TestAuthService:
    """Tests for AuthService."""

    def test_generate_token(self) -> None:
        """Test generating an auth token."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)

        assert token.user_id == 1
        assert token.telegram_id == 12345
        assert token.issued_at <= datetime.now(UTC)
        assert token.expires_at > token.issued_at
        assert token.token_type == "Bearer"
        assert token.jti  # jti is auto-generated (non-empty UUID)

    def test_token_jti_uniqueness(self) -> None:
        """Test that each token gets a unique jti."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token1 = service.generate_token(user_id=1, telegram_id=12345)
        token2 = service.generate_token(user_id=1, telegram_id=12345)
        assert token1.jti != token2.jti

    def test_token_expiry_calculation(self) -> None:
        """Test token expiry is 30 days from issue."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)

        expected_expiry = token.issued_at + timedelta(days=30)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 60

    def test_encode_and_decode_token(self) -> None:
        """Test encoding and decoding a token."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        original_token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(original_token)

        assert isinstance(encoded, str)
        assert len(encoded) > 0
        assert "." in encoded  # JWT format

        decoded = service.decode_token(encoded)
        assert decoded is not None
        assert decoded.user_id == original_token.user_id
        assert decoded.telegram_id == original_token.telegram_id
        assert decoded.jti == original_token.jti

    def test_decode_invalid_token(self) -> None:
        """Test decoding an invalid token."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        decoded = service.decode_token("invalid_token")
        assert decoded is None

    def test_decode_token_with_wrong_signature(self) -> None:
        """Test decoding a token with wrong signature."""
        service1 = AuthService(secret_key="secret1")
        service2 = AuthService(secret_key="secret2")

        token = service1.generate_token(user_id=1, telegram_id=12345)
        encoded = service1.encode_token(token)

        # Try to decode with different secret
        decoded = service2.decode_token(encoded)
        assert decoded is None

    def test_token_is_expired(self) -> None:
        """Test checking if token is expired."""
        token = AuthToken(
            user_id=1,
            telegram_id=12345,
            issued_at=datetime.now(UTC) - timedelta(days=40),
            expires_at=datetime.now(UTC) - timedelta(days=10),
        )
        assert token.is_expired() is True

    def test_token_is_not_expired(self) -> None:
        """Test checking if token is not expired."""
        token = AuthToken(
            user_id=1,
            telegram_id=12345,
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        assert token.is_expired() is False

    def test_decode_expired_token(self) -> None:
        """Test decoding an expired token returns None."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = AuthToken(
            user_id=1,
            telegram_id=12345,
            issued_at=datetime.now(UTC) - timedelta(days=40),
            expires_at=datetime.now(UTC) - timedelta(days=10),
        )
        encoded = service.encode_token(token)
        decoded = service.decode_token(encoded)
        assert decoded is None

    def test_authenticate_request_valid(self) -> None:
        """Test authenticating a valid request."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(token)
        auth_header = f"Bearer {encoded}"

        authenticated = service.authenticate_request(auth_header)
        assert authenticated is not None
        assert authenticated.user_id == 1
        assert authenticated.telegram_id == 12345

    def test_authenticate_request_no_header(self) -> None:
        """Test authenticating with no Authorization header."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        authenticated = service.authenticate_request(None)
        assert authenticated is None

    def test_authenticate_request_invalid_format(self) -> None:
        """Test authenticating with invalid header format."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        authenticated = service.authenticate_request("invalid_format")
        assert authenticated is None

        authenticated = service.authenticate_request("Bearer")
        assert authenticated is None

    def test_check_rate_limit_within_limit(self) -> None:
        """Test rate limiting within allowed limit."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")

        # Make 10 requests (well under limit of 1000)
        for _ in range(10):
            result = service.check_rate_limit(user_id=1)
            assert result is True

    def test_check_rate_limit_exceeded(self) -> None:
        """Test rate limiting when exceeded."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")

        # Manually set rate limit to exceeded
        info = service.get_rate_limit_info(1)
        if info is None:
            # Initialize by making a request
            service.check_rate_limit(user_id=1)
            info = service.get_rate_limit_info(1)

        assert info is not None
        # Set to limit
        info.requests_made = info.limit

        # Next request should fail
        result = service.check_rate_limit(user_id=1)
        assert result is False

    def test_get_rate_limit_info(self) -> None:
        """Test getting rate limit info."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")

        # No info initially
        info = service.get_rate_limit_info(user_id=1)
        assert info is None

        # Make a request to initialize
        service.check_rate_limit(user_id=1)

        # Now should have info
        info = service.get_rate_limit_info(user_id=1)
        assert info is not None
        assert info.user_id == 1
        assert info.requests_made == 1

    def test_rate_limit_resets_after_window(self) -> None:
        """Test rate limit resets after window expires."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")

        # Make a request
        service.check_rate_limit(user_id=1)
        info = service.get_rate_limit_info(1)
        assert info is not None
        assert info.requests_made == 1

        # Manually expire the window
        info.window_start = datetime.now(UTC) - timedelta(seconds=info.window_seconds + 1)

        # Next request should reset the counter
        service.check_rate_limit(user_id=1)
        assert info.requests_made == 1  # Reset and incremented

    def test_token_to_dict_includes_jti(self) -> None:
        """Test that to_dict includes the jti field."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)
        d = token.to_dict()
        assert "jti" in d
        assert d["jti"] == token.jti

    def test_decode_token_revoked(self) -> None:
        """Test that decode_token returns None for revoked tokens."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(token)

        # Revoke the token by adding jti to the blacklist in-memory
        blacklist = get_token_blacklist()
        blacklist._memory_blacklist.add(token.jti)

        try:
            decoded = service.decode_token(encoded)
            assert decoded is None
        finally:
            # Clean up
            blacklist._memory_blacklist.discard(token.jti)

    def test_decode_token_not_revoked(self) -> None:
        """Test that decode_token returns token when not revoked."""
        service = AuthService(secret_key="test-secret-key-for-unit-tests")
        token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(token)

        # Make sure jti is NOT in any blacklist
        blacklist = get_token_blacklist()
        blacklist._memory_blacklist.discard(token.jti)

        decoded = service.decode_token(encoded)
        assert decoded is not None
        assert decoded.jti == token.jti


class TestTokenBlacklist:
    """Tests for JWT token revocation via Redis blacklist."""

    def _make_blacklist(self) -> TokenBlacklist:
        """Create a fresh TokenBlacklist instance."""
        return TokenBlacklist()

    @pytest.mark.asyncio
    async def test_empty_jti_revoke(self) -> None:
        """Test that revoking an empty jti returns False."""
        blacklist = self._make_blacklist()
        result = await blacklist.revoke_token("", datetime.now(UTC) + timedelta(hours=1))
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_jti_check(self) -> None:
        """Test that checking an empty jti returns False."""
        blacklist = self._make_blacklist()
        result = await blacklist.is_token_revoked("")
        assert result is False

    def test_empty_jti_sync_check(self) -> None:
        """Test that sync checking an empty jti returns False."""
        blacklist = self._make_blacklist()
        assert blacklist.is_token_revoked_sync("") is False

    def test_memory_blacklist_add_and_check(self) -> None:
        """Test adding to in-memory blacklist and checking."""
        blacklist = self._make_blacklist()
        jti = "test-jti-12345"

        # Not in blacklist initially
        assert blacklist.is_token_revoked_sync(jti) is False

        # Add to memory blacklist
        blacklist._add_to_memory_blacklist(jti)

        # Now it should be found
        assert blacklist.is_token_revoked_sync(jti) is True

    def test_memory_blacklist_eviction(self) -> None:
        """Test that in-memory blacklist evicts when full."""
        blacklist = self._make_blacklist()
        blacklist.MAX_MEMORY_ENTRIES = 10  # Low threshold for testing

        # Fill the blacklist to the limit
        for i in range(10):
            blacklist._add_to_memory_blacklist(f"jti-{i}")

        assert len(blacklist._memory_blacklist) == 10

        # Adding one more should trigger eviction (drops to ~5 + 1)
        blacklist._add_to_memory_blacklist("jti-overflow")
        assert len(blacklist._memory_blacklist) <= 7  # Half evicted + new one

    @pytest.mark.asyncio
    async def test_revoke_token_redis_unavailable(self) -> None:
        """Test revoking a token when Redis is unavailable (fallback to memory)."""
        blacklist = self._make_blacklist()
        jti = "test-revoke-jti"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        # Mock Redis service to return False (unavailable)
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=False)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = await blacklist.revoke_token(jti, expires_at)

        # Should return False (Redis failed) but add to memory
        assert result is False
        assert jti in blacklist._memory_blacklist

    @pytest.mark.asyncio
    async def test_revoke_token_redis_available(self) -> None:
        """Test revoking a token when Redis is available."""
        blacklist = self._make_blacklist()
        jti = "test-revoke-redis-jti"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        # Mock Redis service to return True (success)
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = await blacklist.revoke_token(jti, expires_at)

        assert result is True
        # Should NOT be in memory blacklist (Redis handled it)
        assert jti not in blacklist._memory_blacklist
        # Verify Redis was called with correct key and TTL
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"aurora:token:blacklist:{jti}"
        assert call_args[0][1] == "revoked"
        assert call_args[1]["ttl"] > 0

    @pytest.mark.asyncio
    async def test_is_token_revoked_async_memory(self) -> None:
        """Test async revocation check finds token in memory blacklist."""
        blacklist = self._make_blacklist()
        jti = "async-memory-jti"
        blacklist._memory_blacklist.add(jti)

        # Mock Redis to return False (not in Redis)
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(return_value=False)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = await blacklist.is_token_revoked(jti)

        # Should find it in memory (fast path, Redis not even checked)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_async_redis(self) -> None:
        """Test async revocation check finds token in Redis."""
        blacklist = self._make_blacklist()
        jti = "async-redis-jti"

        # Mock Redis to return True (found in Redis)
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(return_value=True)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = await blacklist.is_token_revoked(jti)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_async_not_found(self) -> None:
        """Test async revocation check when token is not revoked anywhere."""
        blacklist = self._make_blacklist()
        jti = "not-revoked-jti"

        # Mock Redis to return False
        mock_redis = MagicMock()
        mock_redis.exists = AsyncMock(return_value=False)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = await blacklist.is_token_revoked(jti)

        assert result is False

    def test_is_token_revoked_sync_memory(self) -> None:
        """Test sync revocation check finds token in memory blacklist."""
        blacklist = self._make_blacklist()
        jti = "sync-memory-jti"
        blacklist._memory_blacklist.add(jti)

        assert blacklist.is_token_revoked_sync(jti) is True

    def test_is_token_revoked_sync_redis(self) -> None:
        """Test sync revocation check finds token in Redis."""
        blacklist = self._make_blacklist()
        jti = "sync-redis-jti"

        # Mock Redis service with sync client
        mock_sync_client = MagicMock()
        mock_sync_client.exists.return_value = True
        mock_redis = MagicMock()
        mock_redis._get_sync_client.return_value = mock_sync_client

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = blacklist.is_token_revoked_sync(jti)

        assert result is True

    def test_is_token_revoked_sync_not_found(self) -> None:
        """Test sync revocation check when token is not revoked."""
        blacklist = self._make_blacklist()
        jti = "sync-not-revoked-jti"

        # Mock Redis service with sync client returning False
        mock_sync_client = MagicMock()
        mock_sync_client.exists.return_value = False
        mock_redis = MagicMock()
        mock_redis._get_sync_client.return_value = mock_sync_client

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = blacklist.is_token_revoked_sync(jti)

        assert result is False

    def test_is_token_revoked_sync_redis_unavailable(self) -> None:
        """Test sync revocation check falls back when Redis unavailable."""
        blacklist = self._make_blacklist()
        jti = "sync-no-redis-jti"

        # Mock Redis service with no sync client
        mock_redis = MagicMock()
        mock_redis._get_sync_client.return_value = None

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            result = blacklist.is_token_revoked_sync(jti)

        # Not in memory, Redis unavailable -> not revoked
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_token_ttl_calculation(self) -> None:
        """Test that TTL is correctly calculated from expires_at."""
        blacklist = self._make_blacklist()
        jti = "ttl-test-jti"
        # Token expires in exactly 2 hours
        expires_at = datetime.now(UTC) + timedelta(hours=2)

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            await blacklist.revoke_token(jti, expires_at)

        call_args = mock_redis.set.call_args
        ttl = call_args[1]["ttl"]
        # TTL should be approximately 7200 seconds (2 hours)
        assert 7100 < ttl <= 7200

    @pytest.mark.asyncio
    async def test_revoke_token_minimum_ttl(self) -> None:
        """Test that TTL is at least 1 second even for nearly-expired tokens."""
        blacklist = self._make_blacklist()
        jti = "min-ttl-jti"
        # Token already expired 10 seconds ago
        expires_at = datetime.now(UTC) - timedelta(seconds=10)

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch.object(blacklist, "_get_redis_service", return_value=mock_redis):
            await blacklist.revoke_token(jti, expires_at)

        call_args = mock_redis.set.call_args
        ttl = call_args[1]["ttl"]
        # TTL should be clamped to minimum of 1
        assert ttl == 1


class TestGetTokenBlacklist:
    """Tests for the get_token_blacklist singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """Test that get_token_blacklist returns the same instance."""
        bl1 = get_token_blacklist()
        bl2 = get_token_blacklist()
        assert bl1 is bl2

    def test_singleton_is_token_blacklist(self) -> None:
        """Test that singleton is a TokenBlacklist instance."""
        bl = get_token_blacklist()
        assert isinstance(bl, TokenBlacklist)
