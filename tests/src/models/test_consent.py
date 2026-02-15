"""
Unit tests for the Consent module.

These tests verify the functionality of:
- ConsentRecord model (fields, table structure)
- ConsentStatus enum
- ConsentValidationResult named tuple
- ConsentService (create, verify, validate, withdraw, version, history, reconsent)

Uses an in-memory SQLite database with a real SQLAlchemy session.
"""

import hashlib
import hmac
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.consent import (
    ConsentRecord,
    ConsentService,
    ConsentStatus,
    ConsentValidationResult,
)

# =============================================================================
# Test Fixtures
# =============================================================================

HMAC_SECRET = "test-hmac-secret-for-consent-tests"

# The db_session fixture is provided by conftest.py (tests/conftest.py).
# It creates an in-memory SQLite database with all model tables.


def _insert_test_user(session: Session, telegram_id: str, language: str = "en") -> int:
    """Insert a test user via raw SQL and return the user ID."""
    result = session.execute(
        text(
            "INSERT INTO users (telegram_id, language, timezone, processing_restriction, created_at, updated_at) "
            "VALUES (:tid, :lang, 'UTC', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"tid": telegram_id, "lang": language},
    )
    session.commit()
    return result.lastrowid


@pytest.fixture
def consent_service(db_session: Session) -> ConsentService:
    """Create a ConsentService with the test session and HMAC secret."""
    return ConsentService(session=db_session, hmac_secret=HMAC_SECRET)


@pytest.fixture
def user_id(db_session: Session) -> int:
    """Create a test user and return the user ID."""
    return _insert_test_user(db_session, "hashed_telegram_id_12345", "en")


@pytest.fixture
def second_user_id(db_session: Session) -> int:
    """Create a second test user and return the user ID."""
    return _insert_test_user(db_session, "hashed_telegram_id_67890", "de")


# =============================================================================
# TestConsentStatus
# =============================================================================


class TestConsentStatus:
    """Test the ConsentStatus enum."""

    def test_valid_value(self):
        """VALID has value 'valid'."""
        assert ConsentStatus.VALID.value == "valid"

    def test_not_given_value(self):
        """NOT_GIVEN has value 'not_given'."""
        assert ConsentStatus.NOT_GIVEN.value == "not_given"

    def test_withdrawn_value(self):
        """WITHDRAWN has value 'withdrawn'."""
        assert ConsentStatus.WITHDRAWN.value == "withdrawn"

    def test_expired_value(self):
        """EXPIRED has value 'expired'."""
        assert ConsentStatus.EXPIRED.value == "expired"

    def test_has_four_members(self):
        """ConsentStatus has 4 members (VALID, NOT_GIVEN, WITHDRAWN, EXPIRED)."""
        assert len(ConsentStatus) == 4


# =============================================================================
# TestConsentValidationResult
# =============================================================================


class TestConsentValidationResult:
    """Test the ConsentValidationResult named tuple."""

    def test_create_valid_result(self):
        """Can create a valid ConsentValidationResult."""
        now = datetime.now(UTC)
        result = ConsentValidationResult(
            status=ConsentStatus.VALID,
            consent_given_at=now,
            consent_withdrawn_at=None,
            consent_version="1.0",
            message="Consent is valid",
        )
        assert result.status == ConsentStatus.VALID
        assert result.consent_given_at == now
        assert result.consent_withdrawn_at is None
        assert result.consent_version == "1.0"
        assert result.message == "Consent is valid"

    def test_create_not_given_result(self):
        """Can create a NOT_GIVEN ConsentValidationResult."""
        result = ConsentValidationResult(
            status=ConsentStatus.NOT_GIVEN,
            consent_given_at=None,
            consent_withdrawn_at=None,
            consent_version=None,
            message="No consent record found",
        )
        assert result.status == ConsentStatus.NOT_GIVEN
        assert result.consent_given_at is None

    def test_is_named_tuple(self):
        """ConsentValidationResult is a NamedTuple with correct fields."""
        result = ConsentValidationResult(
            status=ConsentStatus.VALID,
            consent_given_at=None,
            consent_withdrawn_at=None,
            consent_version="1.0",
            message="test",
        )
        assert hasattr(result, "_fields")
        assert "status" in result._fields
        assert "consent_given_at" in result._fields
        assert "consent_withdrawn_at" in result._fields
        assert "consent_version" in result._fields
        assert "message" in result._fields


# =============================================================================
# TestConsentRecord
# =============================================================================


class TestConsentRecord:
    """Test the ConsentRecord SQLAlchemy model."""

    def test_create_consent_record_in_db(self, db_session: Session, user_id: int):
        """ConsentRecord can be persisted to the database."""
        record = ConsentRecord(
            user_id=user_id,
            consent_version="1.0",
            consent_language="en",
            consent_given_at=datetime.now(UTC),
            ip_hash="abc123",
            consent_text_hash="def456",
        )
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)

        assert record.id is not None
        assert record.user_id == user_id
        assert record.consent_version == "1.0"
        assert record.consent_language == "en"
        assert record.consent_withdrawn_at is None

    def test_consent_record_tablename(self):
        """ConsentRecord uses 'consent_records' table name."""
        assert ConsentRecord.__tablename__ == "consent_records"

    def test_consent_record_repr(self, db_session: Session, user_id: int):
        """ConsentRecord __repr__ returns a readable string."""
        record = ConsentRecord(
            user_id=user_id,
            consent_version="2.0",
            consent_language="de",
            consent_given_at=datetime.now(UTC),
            ip_hash="hash",
            consent_text_hash="text_hash",
        )
        db_session.add(record)
        db_session.commit()

        repr_str = repr(record)
        assert "ConsentRecord" in repr_str
        assert "2.0" in repr_str


# =============================================================================
# TestConsentServiceInit
# =============================================================================


class TestConsentServiceInit:
    """Test ConsentService initialization."""

    def test_init_with_hmac_secret(self, db_session: Session):
        """ConsentService accepts an explicit hmac_secret."""
        service = ConsentService(session=db_session, hmac_secret="my-secret")
        assert service._hmac_secret == "my-secret"

    def test_init_without_hmac_secret_uses_env(self, db_session: Session):
        """ConsentService falls back to AURORA_HMAC_SECRET env var."""
        os.environ["AURORA_HMAC_SECRET"] = "env-secret"
        try:
            service = ConsentService(session=db_session)
            assert service._hmac_secret == "env-secret"
        finally:
            del os.environ["AURORA_HMAC_SECRET"]

    def test_init_without_hmac_secret_or_env_raises(self, db_session: Session):
        """ConsentService raises ValueError when no HMAC secret is available."""
        # Ensure env var is not set
        os.environ.pop("AURORA_HMAC_SECRET", None)
        with pytest.raises(ValueError, match="AURORA_HMAC_SECRET"):
            ConsentService(session=db_session)


# =============================================================================
# TestConsentServiceCreate
# =============================================================================


class TestConsentServiceCreate:
    """Test ConsentService.create_consent_record()."""

    def test_create_consent_record(self, consent_service: ConsentService, user_id: int):
        """Create a consent record and verify fields."""
        record = consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="192.168.1.1",
            consent_text="I agree to data processing.",
        )

        assert record is not None
        assert record.id is not None
        assert record.user_id == user_id
        assert record.consent_version == "1.0"
        assert record.consent_language == "en"
        assert record.consent_given_at is not None
        assert record.consent_withdrawn_at is None

    def test_create_consent_hashes_ip(self, consent_service: ConsentService, user_id: int):
        """IP address is stored as HMAC-SHA256 hash, not plaintext."""
        ip = "10.0.0.1"
        record = consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip=ip,
            consent_text="consent text",
        )

        # IP should be hashed, not plaintext
        assert record.ip_hash != ip
        expected_hash = hmac.new(
            HMAC_SECRET.encode("utf-8"),
            ip.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert record.ip_hash == expected_hash

    def test_create_consent_hashes_text(self, consent_service: ConsentService, user_id: int):
        """Consent text is stored as SHA256 hash."""
        consent_text = "I agree to all terms."
        record = consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text=consent_text,
        )

        expected_hash = hashlib.sha256(consent_text.encode("utf-8")).hexdigest()
        assert record.consent_text_hash == expected_hash

    def test_create_consent_invalid_user_id(self, consent_service: ConsentService):
        """Creating consent with non-positive user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            consent_service.create_consent_record(
                user_id=0,
                version="1.0",
                language="en",
                ip="1.2.3.4",
                consent_text="text",
            )

    def test_create_consent_negative_user_id(self, consent_service: ConsentService):
        """Creating consent with negative user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            consent_service.create_consent_record(
                user_id=-5,
                version="1.0",
                language="en",
                ip="1.2.3.4",
                consent_text="text",
            )

    def test_create_consent_empty_version_raises(self, consent_service: ConsentService, user_id: int):
        """Creating consent with empty version raises ValueError."""
        with pytest.raises(ValueError, match="consent_version cannot be empty"):
            consent_service.create_consent_record(
                user_id=user_id,
                version="",
                language="en",
                ip="1.2.3.4",
                consent_text="text",
            )

    def test_create_consent_empty_language_raises(self, consent_service: ConsentService, user_id: int):
        """Creating consent with empty language raises ValueError."""
        with pytest.raises(ValueError, match="consent_language cannot be empty"):
            consent_service.create_consent_record(
                user_id=user_id,
                version="1.0",
                language="",
                ip="1.2.3.4",
                consent_text="text",
            )

    def test_create_consent_updates_existing_active(
        self, consent_service: ConsentService, user_id: int
    ):
        """Creating consent when active consent exists updates the existing record."""
        # Create first consent
        record1 = consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="original text",
        )
        record1_id = record1.id

        # Create second consent for same user (should update, not duplicate)
        record2 = consent_service.create_consent_record(
            user_id=user_id,
            version="2.0",
            language="de",
            ip="5.6.7.8",
            consent_text="updated text",
        )

        # Should be the same record, updated
        assert record2.id == record1_id
        assert record2.consent_version == "2.0"
        assert record2.consent_language == "de"


# =============================================================================
# TestConsentServiceVerify
# =============================================================================


class TestConsentServiceVerify:
    """Test ConsentService.verify_consent()."""

    def test_verify_consent_valid(self, consent_service: ConsentService, user_id: int):
        """verify_consent returns True for active consent."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        assert consent_service.verify_consent(user_id) is True

    def test_verify_consent_no_record(self, consent_service: ConsentService, user_id: int):
        """verify_consent returns False when no consent record exists."""
        assert consent_service.verify_consent(user_id) is False

    def test_verify_consent_withdrawn(self, consent_service: ConsentService, user_id: int):
        """verify_consent returns False after consent is withdrawn."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        consent_service.withdraw_consent(user_id)
        assert consent_service.verify_consent(user_id) is False

    def test_verify_consent_invalid_user_id(self, consent_service: ConsentService):
        """verify_consent returns False for non-positive user_id."""
        assert consent_service.verify_consent(0) is False
        assert consent_service.verify_consent(-1) is False


# =============================================================================
# TestConsentServiceValidate
# =============================================================================


class TestConsentServiceValidate:
    """Test ConsentService.validate_consent()."""

    def test_validate_valid_consent(self, consent_service: ConsentService, user_id: int):
        """validate_consent returns VALID status for active consent."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        result = consent_service.validate_consent(user_id)

        assert result.status == ConsentStatus.VALID
        assert result.consent_given_at is not None
        assert result.consent_withdrawn_at is None
        assert result.consent_version == "1.0"
        assert "valid" in result.message.lower()

    def test_validate_no_consent(self, consent_service: ConsentService, user_id: int):
        """validate_consent returns NOT_GIVEN when no consent exists."""
        result = consent_service.validate_consent(user_id)

        assert result.status == ConsentStatus.NOT_GIVEN
        assert result.consent_given_at is None
        assert result.consent_version is None

    def test_validate_withdrawn_consent(self, consent_service: ConsentService, user_id: int):
        """validate_consent returns WITHDRAWN after withdrawal."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        consent_service.withdraw_consent(user_id)

        result = consent_service.validate_consent(user_id)

        assert result.status == ConsentStatus.WITHDRAWN
        assert result.consent_withdrawn_at is not None
        assert result.consent_version == "1.0"

    def test_validate_invalid_user_id(self, consent_service: ConsentService):
        """validate_consent returns NOT_GIVEN for invalid user_id."""
        result = consent_service.validate_consent(0)
        assert result.status == ConsentStatus.NOT_GIVEN
        assert result.message == "Invalid user ID"

    def test_validate_negative_user_id(self, consent_service: ConsentService):
        """validate_consent returns NOT_GIVEN for negative user_id."""
        result = consent_service.validate_consent(-10)
        assert result.status == ConsentStatus.NOT_GIVEN


# =============================================================================
# TestConsentServiceWithdraw
# =============================================================================


class TestConsentServiceWithdraw:
    """Test ConsentService.withdraw_consent()."""

    def test_withdraw_consent(self, consent_service: ConsentService, user_id: int):
        """Withdrawing consent sets withdrawn_at timestamp."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        consent_service.withdraw_consent(user_id)

        record = consent_service.get_consent_record(user_id)
        assert record is not None
        assert record.consent_withdrawn_at is not None

    def test_withdraw_consent_invalid_user_id(self, consent_service: ConsentService):
        """Withdrawing consent with non-positive user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            consent_service.withdraw_consent(0)

    def test_withdraw_consent_no_active_record(self, consent_service: ConsentService, user_id: int):
        """Withdrawing consent without active record raises RuntimeError."""
        with pytest.raises(RuntimeError, match="No active consent record found"):
            consent_service.withdraw_consent(user_id)

    def test_withdraw_already_withdrawn(self, consent_service: ConsentService, user_id: int):
        """Withdrawing consent twice raises RuntimeError on second call."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="I agree.",
        )
        consent_service.withdraw_consent(user_id)

        with pytest.raises(RuntimeError, match="No active consent record found"):
            consent_service.withdraw_consent(user_id)


# =============================================================================
# TestConsentServiceGetVersion
# =============================================================================


class TestConsentServiceGetVersion:
    """Test ConsentService.get_consent_version()."""

    def test_get_consent_version(self, consent_service: ConsentService, user_id: int):
        """get_consent_version returns version string for active consent."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="2.5",
            language="en",
            ip="1.2.3.4",
            consent_text="consent",
        )
        assert consent_service.get_consent_version(user_id) == "2.5"

    def test_get_consent_version_no_record(self, consent_service: ConsentService, user_id: int):
        """get_consent_version returns None when no consent exists."""
        assert consent_service.get_consent_version(user_id) is None

    def test_get_consent_version_withdrawn(self, consent_service: ConsentService, user_id: int):
        """get_consent_version returns None after withdrawal."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="consent",
        )
        consent_service.withdraw_consent(user_id)
        assert consent_service.get_consent_version(user_id) is None

    def test_get_consent_version_invalid_user_id(self, consent_service: ConsentService):
        """get_consent_version returns None for non-positive user_id."""
        assert consent_service.get_consent_version(0) is None
        assert consent_service.get_consent_version(-1) is None


# =============================================================================
# TestConsentServiceGetRecord
# =============================================================================


class TestConsentServiceGetRecord:
    """Test ConsentService.get_consent_record()."""

    def test_get_consent_record_exists(self, consent_service: ConsentService, user_id: int):
        """get_consent_record returns the most recent record."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text",
        )
        record = consent_service.get_consent_record(user_id)

        assert record is not None
        assert record.user_id == user_id
        assert record.consent_version == "1.0"

    def test_get_consent_record_not_found(self, consent_service: ConsentService, user_id: int):
        """get_consent_record returns None when no record exists."""
        assert consent_service.get_consent_record(user_id) is None


# =============================================================================
# TestConsentServiceGetHistory
# =============================================================================


class TestConsentServiceGetHistory:
    """Test ConsentService.get_consent_history()."""

    def test_get_consent_history_empty(self, consent_service: ConsentService, user_id: int):
        """get_consent_history returns empty list when no records exist."""
        history = consent_service.get_consent_history(user_id)
        assert history == []

    def test_get_consent_history_single(self, consent_service: ConsentService, user_id: int):
        """get_consent_history returns single record."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text",
        )
        history = consent_service.get_consent_history(user_id)
        assert len(history) == 1

    def test_get_consent_history_multiple(
        self,
        consent_service: ConsentService,
        user_id: int,
        db_session: Session,
    ):
        """get_consent_history returns all records including withdrawn ones."""
        # Create first consent and withdraw it
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text v1",
        )
        consent_service.withdraw_consent(user_id)

        # Create second consent (new record since old one is withdrawn)
        consent_service.create_consent_record(
            user_id=user_id,
            version="2.0",
            language="de",
            ip="5.6.7.8",
            consent_text="text v2",
        )

        history = consent_service.get_consent_history(user_id)
        assert len(history) == 2

    def test_get_consent_history_different_users(
        self,
        consent_service: ConsentService,
        user_id: int,
        second_user_id: int,
    ):
        """get_consent_history only returns records for the specified user."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text",
        )
        consent_service.create_consent_record(
            user_id=second_user_id,
            version="1.0",
            language="de",
            ip="5.6.7.8",
            consent_text="text",
        )

        history_user1 = consent_service.get_consent_history(user_id)
        history_user2 = consent_service.get_consent_history(second_user_id)

        assert len(history_user1) == 1
        assert len(history_user2) == 1
        assert history_user1[0].user_id == user_id
        assert history_user2[0].user_id == second_user_id


# =============================================================================
# TestConsentServiceReconsent
# =============================================================================


class TestConsentServiceReconsent:
    """Test ConsentService.reconsent()."""

    def test_reconsent_creates_new_record(
        self, consent_service: ConsentService, user_id: int
    ):
        """Reconsent after withdrawal creates a new consent record."""
        # Initial consent
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="original",
        )
        consent_service.withdraw_consent(user_id)

        # Verify withdrawn
        assert consent_service.verify_consent(user_id) is False

        # Reconsent
        new_record = consent_service.reconsent(
            user_id=user_id,
            version="2.0",
            language="en",
            ip="9.8.7.6",
            consent_text="new consent text",
        )

        assert new_record is not None
        assert new_record.consent_version == "2.0"
        assert new_record.consent_withdrawn_at is None
        assert consent_service.verify_consent(user_id) is True

    def test_reconsent_without_prior_withdrawal(
        self, consent_service: ConsentService, user_id: int
    ):
        """Reconsent when active consent exists updates the existing record."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="original",
        )

        # Reconsent without withdrawing first - should update existing
        record = consent_service.reconsent(
            user_id=user_id,
            version="2.0",
            language="de",
            ip="5.6.7.8",
            consent_text="updated",
        )

        assert record.consent_version == "2.0"
        assert record.consent_language == "de"
        assert consent_service.verify_consent(user_id) is True


# =============================================================================
# TestConsentServicePrivateHelpers
# =============================================================================


class TestConsentServicePrivateHelpers:
    """Test ConsentService._get_active_consent()."""

    def test_get_active_consent_exists(self, consent_service: ConsentService, user_id: int):
        """_get_active_consent returns the active record."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text",
        )
        active = consent_service._get_active_consent(user_id)
        assert active is not None
        assert active.consent_withdrawn_at is None

    def test_get_active_consent_none(self, consent_service: ConsentService, user_id: int):
        """_get_active_consent returns None when no active consent exists."""
        assert consent_service._get_active_consent(user_id) is None

    def test_get_active_consent_after_withdrawal(
        self, consent_service: ConsentService, user_id: int
    ):
        """_get_active_consent returns None after withdrawal."""
        consent_service.create_consent_record(
            user_id=user_id,
            version="1.0",
            language="en",
            ip="1.2.3.4",
            consent_text="text",
        )
        consent_service.withdraw_consent(user_id)

        assert consent_service._get_active_consent(user_id) is None


# =============================================================================
# TestConsentServiceHashing
# =============================================================================


class TestConsentServiceHashing:
    """Test ConsentService._hash_ip() and _hash_consent_text()."""

    def test_hash_ip_deterministic(self, consent_service: ConsentService):
        """Same IP always produces the same hash."""
        hash1 = consent_service._hash_ip("192.168.1.1")
        hash2 = consent_service._hash_ip("192.168.1.1")
        assert hash1 == hash2

    def test_hash_ip_different_ips_different_hashes(self, consent_service: ConsentService):
        """Different IPs produce different hashes."""
        hash1 = consent_service._hash_ip("192.168.1.1")
        hash2 = consent_service._hash_ip("10.0.0.1")
        assert hash1 != hash2

    def test_hash_consent_text_deterministic(self, consent_service: ConsentService):
        """Same consent text always produces the same hash."""
        hash1 = consent_service._hash_consent_text("I agree to terms.")
        hash2 = consent_service._hash_consent_text("I agree to terms.")
        assert hash1 == hash2

    def test_hash_consent_text_uses_sha256(self, consent_service: ConsentService):
        """Consent text hash matches SHA256."""
        text = "I consent to data processing."
        result = consent_service._hash_consent_text(text)
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert result == expected
