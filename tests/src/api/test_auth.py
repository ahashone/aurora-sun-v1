"""
Tests for API Authentication (src/api/auth.py).

Tests:
- Token generation
- Token encoding/decoding
- Token validation
- Rate limiting
- Request authentication
"""

from datetime import UTC, datetime, timedelta

from src.api.auth import AuthService, AuthToken


class TestAuthService:
    """Tests for AuthService."""

    def test_generate_token(self) -> None:
        """Test generating an auth token."""
        service = AuthService()
        token = service.generate_token(user_id=1, telegram_id=12345)

        assert token.user_id == 1
        assert token.telegram_id == 12345
        assert token.issued_at <= datetime.now(UTC)
        assert token.expires_at > token.issued_at
        assert token.token_type == "Bearer"

    def test_token_expiry_calculation(self) -> None:
        """Test token expiry is 30 days from issue."""
        service = AuthService()
        token = service.generate_token(user_id=1, telegram_id=12345)

        expected_expiry = token.issued_at + timedelta(days=30)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 60

    def test_encode_and_decode_token(self) -> None:
        """Test encoding and decoding a token."""
        service = AuthService()
        original_token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(original_token)

        assert isinstance(encoded, str)
        assert len(encoded) > 0
        assert "." in encoded  # JWT format

        decoded = service.decode_token(encoded)
        assert decoded is not None
        assert decoded.user_id == original_token.user_id
        assert decoded.telegram_id == original_token.telegram_id

    def test_decode_invalid_token(self) -> None:
        """Test decoding an invalid token."""
        service = AuthService()
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
        service = AuthService()
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
        service = AuthService()
        token = service.generate_token(user_id=1, telegram_id=12345)
        encoded = service.encode_token(token)
        auth_header = f"Bearer {encoded}"

        authenticated = service.authenticate_request(auth_header)
        assert authenticated is not None
        assert authenticated.user_id == 1
        assert authenticated.telegram_id == 12345

    def test_authenticate_request_no_header(self) -> None:
        """Test authenticating with no Authorization header."""
        service = AuthService()
        authenticated = service.authenticate_request(None)
        assert authenticated is None

    def test_authenticate_request_invalid_format(self) -> None:
        """Test authenticating with invalid header format."""
        service = AuthService()
        authenticated = service.authenticate_request("invalid_format")
        assert authenticated is None

        authenticated = service.authenticate_request("Bearer")
        assert authenticated is None

    def test_check_rate_limit_within_limit(self) -> None:
        """Test rate limiting within allowed limit."""
        service = AuthService()

        # Make 10 requests (well under limit of 1000)
        for _ in range(10):
            result = service.check_rate_limit(user_id=1)
            assert result is True

    def test_check_rate_limit_exceeded(self) -> None:
        """Test rate limiting when exceeded."""
        service = AuthService()

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
        service = AuthService()

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
        service = AuthService()

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
