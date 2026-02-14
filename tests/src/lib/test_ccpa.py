"""
Tests for CCPA Compliance Module (src/lib/ccpa.py).

Tests:
- Data category disclosure
- Right to Know requests
- Right to Delete requests
- Right to Opt-Out (Do Not Sell)
- Request verification
- 45-day deadline tracking
"""

from datetime import UTC, datetime, timedelta

from src.lib.ccpa import (
    CCPARequestStatus,
    CCPARequestType,
    CCPAService,
    DoNotSellStatus,
)


class TestCCPAService:
    """Tests for CCPAService."""

    def test_get_data_categories(self, db_session) -> None:
        """Test getting CCPA data categories."""
        service = CCPAService(db_session)
        categories = service.get_data_categories()

        assert len(categories) >= 4  # At least 4 categories
        category_names = [cat.category_name for cat in categories]
        assert "Identifiers" in category_names
        assert "Usage Data" in category_names
        assert "Health Information" in category_names
        assert "Financial Information" in category_names

        # Verify none are marked as "sold"
        for cat in categories:
            assert cat.sold is False

    def test_create_verification_challenge(self, db_session) -> None:
        """Test creating a verification challenge."""
        service = CCPAService(db_session)
        challenge = service.create_verification_challenge(
            user_id=1, telegram_id=12345
        )

        assert challenge.user_id == 1
        assert challenge.telegram_id == 12345
        assert len(challenge.verification_code) == 6
        assert challenge.verification_code.isdigit()
        assert challenge.attempts == 0
        assert challenge.expires_at > challenge.created_at

    def test_verify_challenge_success(self, db_session) -> None:
        """Test successful verification."""
        service = CCPAService(db_session)
        challenge = service.create_verification_challenge(
            user_id=1, telegram_id=12345
        )

        # Verify with correct code
        result = service.verify_challenge(
            challenge.challenge_id, challenge.verification_code
        )
        assert result is True
        assert challenge.attempts == 1

    def test_verify_challenge_wrong_code(self, db_session) -> None:
        """Test verification with wrong code."""
        service = CCPAService(db_session)
        challenge = service.create_verification_challenge(
            user_id=1, telegram_id=12345
        )

        # Verify with wrong code
        result = service.verify_challenge(challenge.challenge_id, "000000")
        assert result is False
        assert challenge.attempts == 1

    def test_verify_challenge_expired(self, db_session) -> None:
        """Test verification of expired challenge."""
        service = CCPAService(db_session)
        challenge = service.create_verification_challenge(
            user_id=1, telegram_id=12345
        )

        # Manually expire the challenge
        challenge.expires_at = datetime.now(UTC) - timedelta(minutes=1)

        result = service.verify_challenge(
            challenge.challenge_id, challenge.verification_code
        )
        assert result is False

    def test_verify_challenge_max_attempts(self, db_session) -> None:
        """Test verification fails after max attempts."""
        service = CCPAService(db_session)
        challenge = service.create_verification_challenge(
            user_id=1, telegram_id=12345
        )

        # Exhaust attempts
        for _ in range(3):
            service.verify_challenge(challenge.challenge_id, "000000")

        # Should fail even with correct code
        result = service.verify_challenge(
            challenge.challenge_id, challenge.verification_code
        )
        assert result is False

    def test_submit_right_to_know_request(self, db_session) -> None:
        """Test submitting a Right to Know request."""
        service = CCPAService(db_session)
        request = service.submit_right_to_know_request(
            user_id=1, telegram_id=12345
        )

        assert request.user_id == 1
        assert request.telegram_id == 12345
        assert request.request_type == CCPARequestType.RIGHT_TO_KNOW.value
        assert request.status == CCPARequestStatus.PENDING_VERIFICATION.value
        assert request.verification_challenge_id is not None
        assert request.deadline > request.created_at

        # Check 45-day deadline
        expected_deadline = request.created_at + timedelta(days=45)
        assert abs((request.deadline - expected_deadline).total_seconds()) < 60

    def test_submit_right_to_delete_request(self, db_session) -> None:
        """Test submitting a Right to Delete request."""
        service = CCPAService(db_session)
        request = service.submit_right_to_delete_request(
            user_id=1, telegram_id=12345
        )

        assert request.user_id == 1
        assert request.request_type == CCPARequestType.RIGHT_TO_DELETE.value
        assert request.status == CCPARequestStatus.PENDING_VERIFICATION.value
        assert request.deadline > request.created_at

    def test_opt_out_of_sale_new_preference(self, db_session) -> None:
        """Test opting out of sale (new preference)."""
        service = CCPAService(db_session)
        pref = service.opt_out_of_sale(user_id=1, telegram_id=12345)

        assert pref.user_id == 1
        assert pref.telegram_id == 12345
        assert pref.status == DoNotSellStatus.OPTED_OUT.value
        assert pref.opted_out_at is not None
        assert pref.opted_in_at is None

    def test_opt_out_of_sale_existing_preference(self, db_session) -> None:
        """Test opting out when preference already exists."""
        service = CCPAService(db_session)

        # Create initial preference
        pref1 = service.opt_out_of_sale(user_id=1, telegram_id=12345)

        # Opt out again (should update existing)
        pref2 = service.opt_out_of_sale(user_id=1, telegram_id=12345)

        assert pref1.id == pref2.id  # Same record
        assert pref2.status == DoNotSellStatus.OPTED_OUT.value

    def test_get_pending_requests_empty(self, db_session) -> None:
        """Test getting pending requests when none exist."""
        service = CCPAService(db_session)
        requests = service.get_pending_requests()
        assert len(requests) == 0

    def test_get_pending_requests(self, db_session) -> None:
        """Test getting pending requests."""
        service = CCPAService(db_session)

        # Create some requests
        service.submit_right_to_know_request(user_id=1, telegram_id=12345)
        service.submit_right_to_delete_request(user_id=2, telegram_id=67890)

        requests = service.get_pending_requests()
        assert len(requests) == 2

    def test_get_pending_requests_overdue_only(self, db_session) -> None:
        """Test getting only overdue requests."""
        service = CCPAService(db_session)

        # Create a request
        request = service.submit_right_to_know_request(
            user_id=1, telegram_id=12345
        )

        # Make it overdue
        request.deadline = datetime.now(UTC) - timedelta(days=1)
        db_session.commit()

        # Get overdue requests
        overdue = service.get_pending_requests(overdue_only=True)
        assert len(overdue) == 1

        # Get all requests
        all_requests = service.get_pending_requests(overdue_only=False)
        assert len(all_requests) == 1

    def test_data_category_structure(self, db_session) -> None:
        """Test data category structure."""
        service = CCPAService(db_session)
        categories = service.get_data_categories()

        for cat in categories:
            assert hasattr(cat, "category_name")
            assert hasattr(cat, "examples")
            assert hasattr(cat, "sources")
            assert hasattr(cat, "purposes")
            assert hasattr(cat, "third_parties")
            assert hasattr(cat, "sold")
            assert hasattr(cat, "retention_period")
            assert isinstance(cat.examples, list)
            assert isinstance(cat.sources, list)
            assert isinstance(cat.purposes, list)
            assert isinstance(cat.third_parties, list)

    def test_ccpa_response_time_constant(self) -> None:
        """Test CCPA response time constants."""
        assert CCPAService.RESPONSE_TIME_DAYS == 45
        assert CCPAService.EXTENSION_DAYS == 45
        assert CCPAService.VERIFICATION_EXPIRY_MINUTES == 15
