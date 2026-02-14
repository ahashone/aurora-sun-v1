"""
Session Model for Aurora Sun V1.

Data Classification: SENSITIVE (FINDING-034: session metadata may contain
user context that should be encrypted)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 4 (Natural Language Interface)
"""

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    decrypt_for_user,
    encrypt_for_user,
)
from src.models.base import Base

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class Session(Base):
    """
    Session model representing a user's conversational session.

    Session states:
    - idle: No active module flow
    - planning: User is in planning flow
    - review: User is in review flow
    - onboarding: User is in onboarding flow
    - capture: User is capturing items
    - habit: User is in habit module
    - belief: User is in belief module
    - motif: User is in motif module
    - money: User is in money module
    - coaching: User is receiving coaching
    - aurora: User is interacting with Aurora agent

    Attributes:
        id: Primary key
        user_id: Foreign key to users.id
        state: Current session state
        current_module: The active module (if any)
        current_intent: The current intent being processed
        session_metadata: Additional session metadata (JSON, DB column: 'metadata')
        encrypted_metadata: FINDING-034: Encrypted version of sensitive session metadata
        started_at: Session start timestamp
        updated_at: Last activity timestamp

    Data Classification: SENSITIVE (metadata may contain user context)
    """

    __tablename__ = "sessions"

    # Relationships
    user = relationship("User", back_populates="sessions")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Session state
    state = Column(String(30), default="idle", nullable=False)  # idle | planning | review | ...
    current_module = Column(String(30), nullable=True)
    current_intent = Column(String(50), nullable=True)

    # Metadata (JSON for flexibility)
    # Note: The Python attribute is named 'session_metadata' to avoid conflict
    # with SQLAlchemy's reserved 'metadata' attribute on DeclarativeBase.
    # The database column is still named 'metadata'.
    session_metadata = Column("metadata", JSON, nullable=True)

    # FINDING-034: Encrypted metadata column for sensitive session context.
    # Data Classification: SENSITIVE. Contains encrypted JSON of session metadata
    # that may include user-specific context (current topics, recent messages, etc.).
    encrypted_metadata = Column("encrypted_metadata", Text, nullable=True)

    # Timestamps
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Table indices
    __table_args__ = (
        Index("idx_session_user_state", "user_id", "state"),
        Index("idx_session_user_updated", "user_id", "updated_at"),
        Index("idx_session_current_module", "current_module"),
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, user_id={self.user_id}, state={self.state}, module={self.current_module})>"

    def is_active(self, timeout_minutes: int = 30) -> bool:
        """Check if session is still active (within timeout)."""
        if self.state == "idle":
            return False
        now = datetime.now(UTC)
        delta = now - self.updated_at
        return bool(delta.total_seconds() < (timeout_minutes * 60))

    def set_sensitive_metadata(self, metadata: dict[str, Any], user_id: int) -> None:
        """
        FINDING-034: Encrypt and store sensitive session metadata.

        Args:
            metadata: Dictionary of sensitive session metadata
            user_id: The user ID for encryption key derivation
        """
        try:
            plaintext = json.dumps(metadata)
            encrypted = encrypt_for_user(
                plaintext=plaintext,
                user_id=user_id,
                classification=DataClassification.SENSITIVE,
            )
            self.encrypted_metadata = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception:
            logger.warning(
                "Failed to encrypt session metadata for user %d, storing as plaintext fallback",
                user_id,
            )
            self.session_metadata = metadata  # type: ignore[assignment]

    def get_sensitive_metadata(self, user_id: int) -> dict[str, Any] | None:
        """
        FINDING-034: Decrypt and return sensitive session metadata.

        Args:
            user_id: The user ID for decryption key derivation

        Returns:
            Decrypted metadata dictionary, or None if not available
        """
        if self.encrypted_metadata:
            try:
                encrypted_dict = json.loads(str(self.encrypted_metadata))
                encrypted_field = EncryptedField.from_db_dict(encrypted_dict)
                plaintext = decrypt_for_user(encrypted_field, user_id)
                result: dict[str, Any] = json.loads(plaintext)
                return result
            except Exception:
                logger.warning(
                    "Failed to decrypt session metadata for user %d",
                    user_id,
                )
                return None
        # Fallback to plaintext metadata
        if self.session_metadata:
            meta = self.session_metadata
            if isinstance(meta, dict):
                return meta
        return None


__all__ = ["Session"]
