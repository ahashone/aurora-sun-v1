"""
Consent Architecture for Aurora Sun V1.

This module implements GDPR-compliant consent management as specified in
ARCHITECTURE.md Section 10 (Consent Architecture).

The consent system ensures:
- Explicit consent before data processing (GDPR Art. 9(2)(a))
- Audit trail for consent changes
- Consent withdrawal capability
- Version tracking for consent text

Usage:
    from src.models.consent import ConsentService, ConsentRecord, ConsentStatus

    # Check if user has valid consent
    service = ConsentService(session)
    is_valid = service.verify_consent(user_id)

    # Create consent record
    record = service.create_consent_record(
        user_id=1,
        version="1.0",
        language="en",
        ip="192.168.1.1",
        consent_text="I agree to data processing..."
    )

    # Withdraw consent
    service.withdraw_consent(user_id=1)
"""

import hashlib
import hmac
from datetime import UTC, datetime
from enum import Enum
from typing import NamedTuple

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.sql import func

from src.models.base import Base

# ============================================
# Enums and Value Objects
# =========================================


class ConsentStatus(Enum):
    """
    Consent validation status returned by the consent gate.

    Attributes:
        VALID: Consent is active and valid.
        NOT_GIVEN: User has never given consent.
        WITHDRAWN: User has withdrawn consent.
        EXPIRED: Consent version is no longer supported.
    """
    VALID = "valid"
    NOT_GIVEN = "not_given"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class ConsentValidationResult(NamedTuple):
    """
    Result of consent validation.

    Attributes:
        status: The consent status (valid/invalid).
        consent_given_at: When consent was given (if ever).
        consent_withdrawn_at: When consent was withdrawn (if ever).
        consent_version: The version of consent accepted.
        message: Human-readable explanation of the status.
    """
    status: ConsentStatus
    consent_given_at: datetime | None
    consent_withdrawn_at: datetime | None
    consent_version: str | None
    message: str


# ============================================
# Consent Record Model
# =========================================


class ConsentRecord(Base):
    """
    GDPR-compliant consent record for tracking user consent.

    This model stores consent information as specified in ARCHITECTURE.md
    Section 10 (Consent Record). It tracks:
    - When consent was given/withdrawn
    - Which version of consent text was accepted
    - The language in which consent was provided
    - Hashed IP address for audit purposes (not raw IP)
    - Hash of the consent text to prove which version was accepted

    Data Classification: SENSITIVE (contains PII-adjacent data)

    Retention: 5 years after withdrawal (legal obligation per GDPR)
    After retention: Anonymized

    Attributes:
        id: Primary key.
        user_id: Foreign key to the user who gave consent.
        consent_version: Version string (e.g., "1.0") of the consent text.
        consent_language: ISO language code (e.g., "en", "de").
        consent_given_at: Timestamp when consent was granted.
        consent_withdrawn_at: Timestamp when consent was withdrawn (None if active).
        ip_hash: HMAC-SHA256 hash of the user's IP address (not raw IP).
        consent_text_hash: SHA256 hash of the consent text version accepted.

    Note:
        IP is hashed using HMAC with a secret key, not plain SHA256,
        to prevent rainbow table attacks. The secret key should be stored
        in the application config/environment variables.
    """
    __tablename__ = "consent_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Consent version tracking
    consent_version = Column(String(20), nullable=False)  # e.g., "1.0"
    consent_language = Column(String(10), nullable=False)  # e.g., "en", "de"

    # Consent timestamps
    consent_given_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    consent_withdrawn_at = Column(DateTime(timezone=True), nullable=True)

    # Verification hashes (not raw data)
    ip_hash = Column(String(64), nullable=True)  # HMAC-SHA256
    consent_text_hash = Column(String(64), nullable=False)  # SHA256

    # Metadata
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    # Table indices for common queries
    __table_args__ = (
        Index("idx_consent_user_active", "user_id", postgresql_where=(consent_withdrawn_at.is_(None))),
        Index("idx_consent_user_version", "user_id", "consent_version"),
        Index("idx_consent_given_at", "consent_given_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConsentRecord(id={self.id}, user_id={self.user_id}, "
            f"version={self.consent_version}, given_at={self.consent_given_at}, "
            f"withdrawn_at={self.consent_withdrawn_at})>"
        )


# ============================================
# Consent Service
# =========================================


class ConsentService:
    """
    Service for managing GDPR-compliant consent records.

    This service handles all consent-related operations including:
    - Creating consent records with proper hashing
    - Verifying consent validity
    - Withdrawing consent
    - Retrieving consent version information

    The service implements the consent gate validation logic as specified
    in ARCHITECTURE.md Section 10.

    Usage:
        service = ConsentService(db_session)
        is_valid = service.verify_consent(user_id=1)

    Attributes:
        _session: SQLAlchemy database session.
        _hmac_secret: Secret key for IP hashing (HMAC).
    """

    # Default consent version - should be updated with each consent text change
    DEFAULT_CONSENT_VERSION = "1.0"

    def __init__(self, session: DbSession, hmac_secret: str | None = None):
        """
        Initialize the consent service.

        Args:
            session: SQLAlchemy database session for persistence.
            hmac_secret: Secret key for HMAC hashing of IP addresses.
                         REQUIRED - must be provided via environment variable.
        """
        self._session = session
        # F-004: Fail fast if secret not provided - no default fallback
        if hmac_secret is None:
            import os
            hmac_secret = os.environ.get("AURORA_HMAC_SECRET")
            if hmac_secret is None:
                raise ValueError(
                    "AURORA_HMAC_SECRET environment variable is required. "
                    "Do not deploy without setting this secret."
                )
        self._hmac_secret = hmac_secret

    def _hash_ip(self, ip_address: str) -> str:
        """
        Hash an IP address using HMAC-SHA256.

        This prevents rainbow table attacks by using a secret key.
        Raw IP addresses are never stored.

        Args:
            ip_address: The raw IP address string.

        Returns:
            Hex-encoded HMAC-SHA256 hash.
        """
        return hmac.new(
            self._hmac_secret.encode("utf-8"),
            ip_address.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _hash_consent_text(self, consent_text: str) -> str:
        """
        Hash the consent text to prove which version was accepted.

        Args:
            consent_text: The full consent text that the user accepted.

        Returns:
            Hex-encoded SHA256 hash of the consent text.
        """
        return hashlib.sha256(consent_text.encode("utf-8")).hexdigest()

    def create_consent_record(
        self,
        user_id: int,
        version: str,
        language: str,
        ip: str,
        consent_text: str,
    ) -> ConsentRecord:
        """
        Create a new consent record for a user.

        This method is called when a user explicitly agrees to the consent
        text during onboarding or when updating consent.

        Args:
            user_id: The ID of the user giving consent.
            version: The consent version string (e.g., "1.0").
            language: ISO language code (e.g., "en", "de").
            ip: The user's IP address (will be hashed).
            consent_text: The full consent text (will be hashed for verification).

        Returns:
            The created ConsentRecord instance.

        Raises:
            ValueError: If user_id is not positive, version is empty,
                       or language is empty.

        Note:
            If the user already has an active consent record, this will NOT
            create a duplicate. Use verify_consent() first to check.
        """
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not version:
            raise ValueError("consent_version cannot be empty")
        if not language:
            raise ValueError("consent_language cannot be empty")

        # Check if user already has active consent
        existing = self._get_active_consent(user_id)
        if existing:
            # Update existing record instead of creating new one
            existing.consent_given_at = datetime.now(UTC)
            existing.consent_version = version
            existing.consent_language = language
            existing.ip_hash = self._hash_ip(ip)
            existing.consent_text_hash = self._hash_consent_text(consent_text)
            existing.consent_withdrawn_at = None
            self._session.commit()
            return existing

        # Create new consent record
        record = ConsentRecord(
            user_id=user_id,
            consent_version=version,
            consent_language=language,
            consent_given_at=datetime.now(UTC),
            consent_withdrawn_at=None,
            ip_hash=self._hash_ip(ip),
            consent_text_hash=self._hash_consent_text(consent_text),
        )

        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)

        return record

    def verify_consent(self, user_id: int) -> bool:
        """
        Verify if a user has valid, active consent.

        This implements the consent gate validation logic:
        1. Check consent_given_at is not None
        2. Check consent_withdrawn_at is None

        Args:
            user_id: The ID of the user to verify.

        Returns:
            True if consent is valid and active, False otherwise.
        """
        if user_id <= 0:
            return False

        record = self._get_active_consent(user_id)
        if record is None:
            return False

        # Consent is valid if given and not withdrawn
        return (
            record.consent_given_at is not None
            and record.consent_withdrawn_at is None
        )

    def validate_consent(self, user_id: int) -> ConsentValidationResult:
        """
        Validate consent and return detailed status information.

        This method provides comprehensive consent status for debugging,
        logging, and user-facing consent management interfaces.

        Args:
            user_id: The ID of the user to validate.

        Returns:
            ConsentValidationResult with detailed status information.
        """
        if user_id <= 0:
            return ConsentValidationResult(
                status=ConsentStatus.NOT_GIVEN,
                consent_given_at=None,
                consent_withdrawn_at=None,
                consent_version=None,
                message="Invalid user ID",
            )

        # Get the most recent consent record
        record = self._session.query(ConsentRecord).filter(
            ConsentRecord.user_id == user_id
        ).order_by(ConsentRecord.consent_given_at.desc()).first()

        if record is None:
            return ConsentValidationResult(
                status=ConsentStatus.NOT_GIVEN,
                consent_given_at=None,
                consent_withdrawn_at=None,
                consent_version=None,
                message="No consent record found",
            )

        # Check if withdrawn
        if record.consent_withdrawn_at is not None:
            return ConsentValidationResult(
                status=ConsentStatus.WITHDRAWN,
                consent_given_at=record.consent_given_at,
                consent_withdrawn_at=record.consent_withdrawn_at,
                consent_version=record.consent_version,
                message="Consent has been withdrawn",
            )

        # Check if given
        if record.consent_given_at is None:
            return ConsentValidationResult(
                status=ConsentStatus.NOT_GIVEN,
                consent_given_at=None,
                consent_withdrawn_at=None,
                consent_version=None,
                message="Consent was not given",
            )

        # Valid consent
        return ConsentValidationResult(
            status=ConsentStatus.VALID,
            consent_given_at=record.consent_given_at,
            consent_withdrawn_at=None,
            consent_version=record.consent_version,
            message="Consent is valid and active",
        )

    def withdraw_consent(self, user_id: int) -> None:
        """
        Withdraw consent for a user.

        This sets the consent_withdrawn_at timestamp, effectively revoking
        the user's consent. This triggers SW-15 (GDPR Export/Delete) which
        cascades data deletion across all databases.

        Args:
            user_id: The ID of the user withdrawing consent.

        Raises:
            ValueError: If user_id is not positive.
            RuntimeError: If no active consent record exists.

        Note:
            This does NOT delete the consent record itself. Consent records
            are retained for 5 years after withdrawal for legal compliance.
            Only the user's other data is deleted.
        """
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        record = self._get_active_consent(user_id)
        if record is None:
            raise RuntimeError(
                f"No active consent record found for user {user_id}. "
                "Cannot withdraw consent."
            )

        record.consent_withdrawn_at = datetime.now(UTC)
        self._session.commit()

    def get_consent_version(self, user_id: int) -> str | None:
        """
        Get the current consent version for a user.

        Args:
            user_id: The ID of the user.

        Returns:
            The consent version string (e.g., "1.0") if valid consent exists,
            None if no valid consent exists.
        """
        if user_id <= 0:
            return None

        record = self._get_active_consent(user_id)
        if record is None:
            return None

        return record.consent_version

    def get_consent_record(self, user_id: int) -> ConsentRecord | None:
        """
        Get the most recent consent record for a user.

        Args:
            user_id: The ID of the user.

        Returns:
            The most recent ConsentRecord, or None if not found.
        """
        return self._session.query(ConsentRecord).filter(
            ConsentRecord.user_id == user_id
        ).order_by(ConsentRecord.consent_given_at.desc()).first()

    def _get_active_consent(self, user_id: int) -> ConsentRecord | None:
        """
        Get the active (non-withdrawn) consent record for a user.

        Args:
            user_id: The ID of the user.

        Returns:
            The active ConsentRecord, or None if no active consent exists.
        """
        return self._session.query(ConsentRecord).filter(
            ConsentRecord.user_id == user_id,
            ConsentRecord.consent_withdrawn_at.is_(None),
        ).order_by(ConsentRecord.consent_given_at.desc()).first()

    def get_consent_history(self, user_id: int) -> list[ConsentRecord]:
        """
        Get the complete consent history for a user.

        This returns all consent records, including withdrawn ones,
        ordered by consent_given_at descending.

        Args:
            user_id: The ID of the user.

        Returns:
            List of ConsentRecord objects, oldest first.
        """
        return (
            self._session.query(ConsentRecord)
            .filter(ConsentRecord.user_id == user_id)
            .order_by(ConsentRecord.consent_given_at.desc())
            .all()
        )

    def reconsent(
        self,
        user_id: int,
        version: str,
        language: str,
        ip: str,
        consent_text: str,
    ) -> ConsentRecord:
        """
        Process a user's re-consent (after previously withdrawing).

        This is equivalent to creating a new consent record after a withdrawal.

        Args:
            user_id: The ID of the user.
            version: The new consent version.
            language: ISO language code.
            ip: User's IP address (will be hashed).
            consent_text: The consent text (will be hashed).

        Returns:
            The new ConsentRecord instance.
        """
        return self.create_consent_record(
            user_id=user_id,
            version=version,
            language=language,
            ip=ip,
            consent_text=consent_text,
        )


# ============================================
# Consent Gate (Standalone Function)
# =========================================


def check_consent_gate(
    session: DbSession,
    user_id: int,
) -> ConsentValidationResult:
    """
    Check if a user has passed the consent gate.

    This is the main entry point for consent validation in the application.
    It should be called before any data processing that requires consent.

    Args:
        session: SQLAlchemy database session.
        user_id: The ID of the user to check.

    Returns:
        ConsentValidationResult with detailed status.
    """
    service = ConsentService(session)
    return service.validate_consent(user_id)


# ============================================
# Export for convenience
# ============================================

__all__ = [
    "ConsentRecord",
    "ConsentService",
    "ConsentStatus",
    "ConsentValidationResult",
    "check_consent_gate",
]
