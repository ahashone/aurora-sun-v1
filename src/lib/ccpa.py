"""
CCPA Compliance Module for Aurora Sun V1.

Implements CCPA (California Consumer Privacy Act) data subject rights:
- Right to Know (CCPA § 1798.100): What personal information is collected
- Right to Delete (CCPA § 1798.105): Delete personal information
- Right to Opt-Out (CCPA § 1798.120): "Do Not Sell My Personal Information"
- Right to Non-Discrimination (CCPA § 1798.125): No discrimination for exercising rights

Key CCPA Requirements:
- 45-day response time for requests (extendable by 45 days)
- Request verification system (prevent fraudulent requests)
- Privacy policy disclosure of data collection/use/sale
- "Do Not Sell" opt-out mechanism

References:
- ROADMAP 5.3: CCPA Compliance
- ARCHITECTURE.md Section 10: Security & Privacy Architecture
- Parallel structure to GDPR module (src/lib/gdpr.py)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from src.models.base import Base

logger = logging.getLogger(__name__)


class CCPARequestType(Enum):
    """CCPA request types."""

    RIGHT_TO_KNOW = "right_to_know"  # § 1798.100
    RIGHT_TO_DELETE = "right_to_delete"  # § 1798.105
    RIGHT_TO_OPT_OUT = "right_to_opt_out"  # § 1798.120 (Do Not Sell)


class CCPARequestStatus(Enum):
    """CCPA request processing status."""

    PENDING_VERIFICATION = "pending_verification"  # Awaiting user verification
    VERIFIED = "verified"  # User verified, processing can proceed
    IN_PROGRESS = "in_progress"  # Request is being processed
    COMPLETED = "completed"  # Request completed successfully
    DENIED = "denied"  # Request denied (e.g., verification failed)
    EXTENDED = "extended"  # Response time extended by 45 days


class DoNotSellStatus(Enum):
    """Do Not Sell My Personal Information status."""

    OPTED_IN = "opted_in"  # User allows data sale (default)
    OPTED_OUT = "opted_out"  # User opted out of data sale


@dataclass
class CCPADataCategory:
    """
    CCPA data category disclosure.

    CCPA requires disclosure of:
    - Categories of personal information collected
    - Sources from which collected
    - Business/commercial purposes
    - Categories of third parties with whom shared
    """

    category_name: str  # e.g., "Identifiers", "Usage Data", "Health Information"
    examples: list[str]  # e.g., ["name", "email", "telegram_id"]
    sources: list[str]  # e.g., ["Direct from user", "Telegram API"]
    purposes: list[str]  # e.g., ["AI coaching", "Service delivery"]
    third_parties: list[str]  # e.g., ["Anthropic (AI provider)", "None"]
    sold: bool  # Whether this category is sold
    retention_period: str  # e.g., "Until account deletion", "5 years"


@dataclass
class CCPAVerificationChallenge:
    """
    Verification challenge for CCPA requests.

    To prevent fraudulent requests, we must verify the requestor's identity.
    For Telegram users, we use a time-limited verification code.
    """

    challenge_id: str
    user_id: int
    telegram_id: int
    verification_code: str  # 6-digit code sent via Telegram
    created_at: datetime
    expires_at: datetime
    attempts: int = 0  # How many verification attempts
    max_attempts: int = 3


# =============================================================================
# SQLAlchemy Models
# =============================================================================


class CCPARequest(Base):
    """
    SQLAlchemy model for CCPA requests.

    Tracks all CCPA requests (Right to Know, Right to Delete, Right to Opt-Out).
    """

    __tablename__ = "ccpa_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, nullable=False)

    request_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # CCPARequestType
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # CCPARequestStatus

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # 45 days from creation
    extended_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Verification
    verification_challenge_id: Mapped[str | None] = mapped_column(String(100))
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Processing notes
    processing_notes: Mapped[str | None] = mapped_column(Text)

    # Response data (JSON export for Right to Know)
    response_data: Mapped[str | None] = mapped_column(Text)  # JSON string


class DoNotSellPreference(Base):
    """
    SQLAlchemy model for "Do Not Sell My Personal Information" preferences.

    CCPA § 1798.120: Right to opt-out of sale of personal information.

    Note: Aurora Sun V1 does NOT sell personal information to third parties.
    However, CCPA requires providing this opt-out mechanism and documenting
    that no sale occurs.
    """

    __tablename__ = "ccpa_do_not_sell_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=DoNotSellStatus.OPTED_IN.value
    )

    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# =============================================================================
# CCPA Service
# =============================================================================


class CCPAService:
    """
    CCPA compliance service for Aurora Sun V1.

    Handles:
    - Right to Know requests (data export)
    - Right to Delete requests (data deletion)
    - Right to Opt-Out requests (Do Not Sell)
    - Request verification
    - Response time tracking (45-day deadline)
    """

    # CCPA response time: 45 days
    RESPONSE_TIME_DAYS = 45

    # Extension period: additional 45 days
    EXTENSION_DAYS = 45

    # Verification code expiry: 15 minutes
    VERIFICATION_EXPIRY_MINUTES = 15

    def __init__(self, db_session: Session) -> None:
        """
        Initialize CCPA service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self._verification_challenges: dict[str, CCPAVerificationChallenge] = {}

    def get_data_categories(self) -> list[CCPADataCategory]:
        """
        Get all CCPA data categories collected by Aurora Sun V1.

        This disclosure is required for the privacy policy and Right to Know responses.

        Returns:
            List of data categories
        """
        return [
            CCPADataCategory(
                category_name="Identifiers",
                examples=["Name", "Telegram ID", "User ID"],
                sources=["Direct from user", "Telegram API"],
                purposes=["User identification", "Service delivery"],
                third_parties=["None (stored internally only)"],
                sold=False,
                retention_period="Until account deletion",
            ),
            CCPADataCategory(
                category_name="Usage Data",
                examples=["Tasks", "Goals", "Daily reflections"],
                sources=["Direct from user"],
                purposes=["AI coaching", "Progress tracking"],
                third_parties=["Anthropic (AI provider - processing only, not sale)"],
                sold=False,
                retention_period="Until account deletion",
            ),
            CCPADataCategory(
                category_name="Health Information",
                examples=["Energy levels", "Burnout assessments", "Sensory preferences"],
                sources=["Direct from user"],
                purposes=["Personalized coaching", "Neurostate tracking"],
                third_parties=["Anthropic (AI provider - processing only, not sale)"],
                sold=False,
                retention_period="Until account deletion",
            ),
            CCPADataCategory(
                category_name="Financial Information",
                examples=["Income/expense tracking", "Revenue tracking"],
                sources=["Direct from user"],
                purposes=["Financial coaching", "Money management"],
                third_parties=["None"],
                sold=False,
                retention_period="Until account deletion",
            ),
        ]

    def create_verification_challenge(
        self,
        user_id: int,
        telegram_id: int,
    ) -> CCPAVerificationChallenge:
        """
        Create a verification challenge for a CCPA request.

        Args:
            user_id: User ID
            telegram_id: Telegram ID

        Returns:
            Verification challenge
        """
        import random
        import uuid

        challenge_id = str(uuid.uuid4())
        verification_code = f"{random.randint(100000, 999999)}"
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.VERIFICATION_EXPIRY_MINUTES)

        challenge = CCPAVerificationChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            telegram_id=telegram_id,
            verification_code=verification_code,
            created_at=now,
            expires_at=expires_at,
        )

        self._verification_challenges[challenge_id] = challenge

        logger.info(f"Created verification challenge {challenge_id} for user {user_id}")
        return challenge

    def verify_challenge(
        self,
        challenge_id: str,
        verification_code: str,
    ) -> bool:
        """
        Verify a verification challenge.

        Args:
            challenge_id: Challenge ID
            verification_code: User-provided verification code

        Returns:
            True if verified, False otherwise
        """
        challenge = self._verification_challenges.get(challenge_id)
        if challenge is None:
            logger.warning(f"Challenge {challenge_id} not found")
            return False

        if datetime.now(UTC) > challenge.expires_at:
            logger.warning(f"Challenge {challenge_id} expired")
            return False

        challenge.attempts += 1
        if challenge.attempts > challenge.max_attempts:
            logger.warning(f"Challenge {challenge_id} exceeded max attempts")
            return False

        if challenge.verification_code != verification_code:
            logger.warning(f"Challenge {challenge_id} verification failed")
            return False

        logger.info(f"Challenge {challenge_id} verified successfully")
        return True

    def submit_right_to_know_request(
        self,
        user_id: int,
        telegram_id: int,
    ) -> CCPARequest:
        """
        Submit a Right to Know request (CCPA § 1798.100).

        User requests disclosure of what personal information is collected.

        Args:
            user_id: User ID
            telegram_id: Telegram ID

        Returns:
            CCPA request record
        """
        now = datetime.now(UTC)
        deadline = now + timedelta(days=self.RESPONSE_TIME_DAYS)

        # Create verification challenge
        challenge = self.create_verification_challenge(user_id, telegram_id)

        request = CCPARequest(
            user_id=user_id,
            telegram_id=telegram_id,
            request_type=CCPARequestType.RIGHT_TO_KNOW.value,
            status=CCPARequestStatus.PENDING_VERIFICATION.value,
            created_at=now,
            deadline=deadline,
            verification_challenge_id=challenge.challenge_id,
        )

        self.db.add(request)
        self.db.commit()

        logger.info(f"Created Right to Know request for user {user_id}")
        return request

    def submit_right_to_delete_request(
        self,
        user_id: int,
        telegram_id: int,
    ) -> CCPARequest:
        """
        Submit a Right to Delete request (CCPA § 1798.105).

        User requests deletion of all personal information.

        Args:
            user_id: User ID
            telegram_id: Telegram ID

        Returns:
            CCPA request record
        """
        now = datetime.now(UTC)
        deadline = now + timedelta(days=self.RESPONSE_TIME_DAYS)

        # Create verification challenge
        challenge = self.create_verification_challenge(user_id, telegram_id)

        request = CCPARequest(
            user_id=user_id,
            telegram_id=telegram_id,
            request_type=CCPARequestType.RIGHT_TO_DELETE.value,
            status=CCPARequestStatus.PENDING_VERIFICATION.value,
            created_at=now,
            deadline=deadline,
            verification_challenge_id=challenge.challenge_id,
        )

        self.db.add(request)
        self.db.commit()

        logger.info(f"Created Right to Delete request for user {user_id}")
        return request

    def opt_out_of_sale(
        self,
        user_id: int,
        telegram_id: int,
    ) -> DoNotSellPreference:
        """
        Opt out of sale of personal information (CCPA § 1798.120).

        Note: Aurora Sun V1 does NOT sell personal information.
        This is provided for CCPA compliance.

        Args:
            user_id: User ID
            telegram_id: Telegram ID

        Returns:
            Do Not Sell preference record
        """
        now = datetime.now(UTC)

        # Check if preference already exists
        pref = self.db.query(DoNotSellPreference).filter_by(user_id=user_id).first()

        if pref is None:
            # Create new preference
            pref = DoNotSellPreference(
                user_id=user_id,
                telegram_id=telegram_id,
                status=DoNotSellStatus.OPTED_OUT.value,
                opted_out_at=now,
                created_at=now,
                updated_at=now,
            )
            self.db.add(pref)
        else:
            # Update existing preference
            pref.status = DoNotSellStatus.OPTED_OUT.value
            pref.opted_out_at = now
            pref.updated_at = now

        self.db.commit()

        logger.info(f"User {user_id} opted out of sale")
        return pref

    def get_pending_requests(
        self,
        overdue_only: bool = False,
    ) -> list[CCPARequest]:
        """
        Get pending CCPA requests.

        Args:
            overdue_only: If True, only return overdue requests

        Returns:
            List of pending requests
        """
        query = self.db.query(CCPARequest).filter(
            CCPARequest.status.in_([
                CCPARequestStatus.PENDING_VERIFICATION.value,
                CCPARequestStatus.VERIFIED.value,
                CCPARequestStatus.IN_PROGRESS.value,
            ])
        )

        if overdue_only:
            now = datetime.now(UTC)
            query = query.filter(CCPARequest.deadline < now)

        return list(query.all())


__all__ = [
    "CCPAService",
    "CCPARequest",
    "DoNotSellPreference",
    "CCPARequestType",
    "CCPARequestStatus",
    "DoNotSellStatus",
    "CCPADataCategory",
    "CCPAVerificationChallenge",
]
