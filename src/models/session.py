"""
Session Model for Aurora Sun V1.

Data Classification: SENSITIVE (session metadata may contain
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
        encrypted_metadata: Encrypted version of sensitive session metadata (AES-256-GCM)
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

    # Encrypted metadata column for sensitive session context.
    # Data Classification: SENSITIVE. Contains encrypted JSON of session metadata
    # that may include user-specific context (current topics, recent messages, etc.).
    _encrypted_metadata_plaintext = Column("encrypted_metadata", Text, nullable=True)

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

    # =============================================================================
    # Encrypted metadata property (aligned with User.name / SensoryProfile pattern)
    # =============================================================================

    @property
    def encrypted_metadata(self) -> dict[str, Any] | None:
        """Get decrypted sensitive metadata. Data Classification: SENSITIVE.

        Uses the property pattern consistent with User.name, SensoryProfile.modality_loads, etc.
        Falls back to plaintext session_metadata if no encrypted data is available.
        """
        if self._encrypted_metadata_plaintext is None:
            # Fallback to plaintext metadata
            if self.session_metadata:
                meta = self.session_metadata
                if isinstance(meta, dict):
                    return meta
            return None
        try:
            encrypted_dict = json.loads(str(self._encrypted_metadata_plaintext))
            if isinstance(encrypted_dict, dict) and "ciphertext" in encrypted_dict:
                encrypted_field = EncryptedField.from_db_dict(encrypted_dict)
                from src.lib.encryption import get_encryption_service
                svc = get_encryption_service()
                plaintext = svc.decrypt_field(
                    encrypted_field, int(self.user_id), "session_metadata"
                )
                result: dict[str, Any] = json.loads(plaintext)
                return result
            # Non-encrypted JSON fallback
            if isinstance(encrypted_dict, dict):
                return encrypted_dict
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            logger.warning(
                "Failed to decrypt session metadata for user %s",
                self.user_id,
            )
        return None

    @encrypted_metadata.setter
    def encrypted_metadata(self, value: dict[str, Any] | str | None) -> None:
        """Set encrypted sensitive metadata. Data Classification: SENSITIVE.

        Args:
            value: Dictionary of sensitive session metadata to encrypt,
                   a raw JSON string (for backward compat), or None to clear.
        """
        if value is None:
            self._encrypted_metadata_plaintext = None  # type: ignore[assignment]
            return
        # Accept raw string for backward compatibility (e.g., already-serialized JSON)
        if isinstance(value, str):
            self._encrypted_metadata_plaintext = value  # type: ignore[assignment]
            return
        # Encrypt the dict
        try:
            from src.lib.encryption import DataClassification as DC
            from src.lib.encryption import get_encryption_service
            plaintext_json = json.dumps(value)
            encrypted = get_encryption_service().encrypt_field(
                plaintext_json, int(self.user_id), DC.SENSITIVE, "session_metadata"
            )
            self._encrypted_metadata_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception as e:
            logger.error(
                "Encryption failed for session metadata, refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def set_sensitive_metadata(self, metadata: dict[str, Any], user_id: int) -> None:
        """
        Encrypt and store sensitive session metadata (AES-256-GCM).

        Backward-compatible method. Prefer using the encrypted_metadata property
        setter directly for new code.

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
            self._encrypted_metadata_plaintext = json.dumps(encrypted.to_db_dict())  # type: ignore[assignment]
        except Exception:
            logger.warning(
                "Failed to encrypt session metadata for user %d, storing as plaintext fallback",
                user_id,
            )
            self.session_metadata = metadata  # type: ignore[assignment]

    def get_sensitive_metadata(self, user_id: int) -> dict[str, Any] | None:
        """
        Decrypt and return sensitive session metadata.

        Backward-compatible method. Prefer using the encrypted_metadata property
        getter directly for new code.

        Args:
            user_id: The user ID for decryption key derivation

        Returns:
            Decrypted metadata dictionary, or None if not available
        """
        if self._encrypted_metadata_plaintext:
            try:
                encrypted_dict = json.loads(str(self._encrypted_metadata_plaintext))
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
