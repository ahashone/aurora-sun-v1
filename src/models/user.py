"""
User Model for Aurora Sun V1.

Data Classification: SENSITIVE (telegram_id is hashed, name is encrypted)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, event
from sqlalchemy.orm import relationship, selectinload

from src.models.base import Base

logger = logging.getLogger(__name__)

# PERF-009: Sentinel for distinguishing "not cached" from "cached as None"
_SENTINEL = object()


class User(Base):
    """
    User model representing a Telegram user in Aurora Sun V1.

    Attributes:
        id: Primary key
        telegram_id: Hashed Telegram user ID (HMAC-SHA256, never plaintext)
        name: User's display name (encrypted)
        language: ISO language code (e.g., "en", "de")
        timezone: IANA timezone (e.g., "Europe/Berlin")
        working_style_code: Internal segment code (AD | AU | AH | NT | CU)
        encryption_salt: Per-user salt for field encryption
        letta_agent_id: Associated Letta agent ID (if memory is enabled)

    Data Classification: SENSITIVE
    - telegram_id: Hashed with HMAC-SHA256
    - name: Encrypted with AES-256-GCM (per-user key)
    """

    __tablename__ = "users"

    # Relationships
    visions = relationship("Vision", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    daily_plans = relationship("DailyPlan", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    captured_items = relationship("CapturedContent", back_populates="user_relationship", cascade="all, delete-orphan")
    second_brain_entries = relationship("SecondBrainEntry", back_populates="user_relationship", cascade="all, delete-orphan")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)

    # PII - Always hashed, never stored in plaintext
    telegram_id = Column(String(64), unique=True, nullable=False, index=True)

    # User profile - F-002: Encrypted fields using hybrid properties
    # Plaintext stored in DB column, encrypted via property accessors
    _name_plaintext = Column("name", String(255), nullable=True)  # Encrypted storage
    language = Column(String(10), default="en", nullable=False)
    timezone = Column(String(50), default="UTC", nullable=False)

    # Segmentation (internal codes, never shown to users)
    working_style_code = Column(String(2), nullable=True)  # AD | AU | AH | NT | CU

    # Encryption & External Services
    encryption_salt = Column(String(32), nullable=True)
    letta_agent_id = Column(String(64), nullable=True)

    # Timestamps
    created_at = Column(
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
        Index("idx_user_language", "language"),
        Index("idx_user_working_style", "working_style_code"),
        Index("idx_user_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id_hash={self.telegram_id[:8]}..., language={self.language})>"

    # =============================================================================
    # F-002: Encrypted field accessors - DataClassification SENSITIVE
    # =============================================================================
    @property
    def name(self) -> str | None:
        """Get decrypted name (PERF-009: cached after first access)."""
        cached = self.__dict__.get("_cached_name", _SENTINEL)
        if cached is not _SENTINEL:
            return cached  # type: ignore[no-any-return]
        if self._name_plaintext is None:
            self.__dict__["_cached_name"] = None
            return None
        try:
            data = json.loads(str(self._name_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import (
                    EncryptedField,
                    get_encryption_service,
                )
                encrypted = EncryptedField.from_db_dict(data)
                svc = get_encryption_service()
                result = svc.decrypt_field(
                    encrypted, int(self.id), "name"
                )
                self.__dict__["_cached_name"] = result
                return result
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass
        # Plaintext fallback for unencrypted/legacy data or id=None
        fallback: str | None = str(self._name_plaintext) if self._name_plaintext else None
        self.__dict__["_cached_name"] = fallback
        return fallback

    @name.setter
    def name(self, value: str | None) -> None:
        """Set encrypted name."""
        self.__dict__.pop("_cached_name", None)
        if value is None:
            setattr(self, '_name_plaintext', None)
            return
        # Cannot encrypt without user ID (new user before INSERT)
        if self.id is None:
            setattr(self, '_name_plaintext', value)
            return
        try:
            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.id), DataClassification.SENSITIVE, "name"
            )
            setattr(self, '_name_plaintext', json.dumps(encrypted.to_db_dict()))
        except Exception as e:
            logger.error(
                "Encryption failed for field 'name', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    @property
    def segment_display_name(self) -> str:
        """Convert internal segment code to user-facing name."""
        SEGMENT_DISPLAY_NAMES: dict[str, str] = {
            "AD": "ADHD",
            "AU": "Autism",
            "AH": "AuDHD",
            "NT": "Neurotypical",
            "CU": "Custom",
        }
        # working_style_code is a Column[str] at class definition, but str | None at runtime
        code = str(self.working_style_code) if self.working_style_code else None
        return SEGMENT_DISPLAY_NAMES.get(code, "Neurotypical") if code else "Neurotypical"

    # =================================================================
    # PERF-001: Eager loading options for hot-path queries
    # =================================================================
    @classmethod
    def eager_load_options(cls) -> list[object]:
        """Return selectinload options for hot-path relationships.

        Usage:
            session.query(User).options(
                *User.eager_load_options()
            ).filter_by(...)
        """
        return [
            selectinload(cls.goals),
            selectinload(cls.tasks),
            selectinload(cls.visions),
        ]

    @classmethod
    def eager_load_all_options(cls) -> list[object]:
        """Return selectinload options for ALL relationships."""
        return [
            selectinload(cls.goals),
            selectinload(cls.tasks),
            selectinload(cls.visions),
            selectinload(cls.daily_plans),
            selectinload(cls.sessions),
            selectinload(cls.captured_items),
            selectinload(cls.second_brain_entries),
        ]


# =============================================================================
# PERF-005: Event listener cleanup analysis.
# The @event.listens_for decorator below is a class-level listener registered
# once at module import time. SQLAlchemy uses strong references for class-level
# listeners, so it does NOT accumulate across requests. No cleanup needed.
# =============================================================================

# =============================================================================
# Re-encrypt name after INSERT when auto-increment ID is assigned
# =============================================================================
@event.listens_for(User, "after_insert")
def _re_encrypt_name_after_insert(
    mapper: object, connection: object, target: User
) -> None:
    """
    Re-encrypt the name field after INSERT when the user ID is now available.

    When a new User is created, the name setter cannot encrypt because self.id
    is None (auto-increment not yet assigned). After INSERT, the ID exists, so
    we re-encrypt the plaintext name and update the row.
    """
    raw_name = target._name_plaintext
    if raw_name is None or target.id is None:
        return

    # Check if the stored value is already encrypted (JSON with "ciphertext")
    try:
        data = json.loads(str(raw_name))
        if isinstance(data, dict) and "ciphertext" in data:
            return  # Already encrypted, nothing to do
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # The name is plaintext -- encrypt it now that we have the ID
    try:
        from src.lib.encryption import DataClassification, get_encryption_service
        encrypted = get_encryption_service().encrypt_field(
            str(raw_name), int(target.id), DataClassification.SENSITIVE, "name"
        )
        encrypted_json = json.dumps(encrypted.to_db_dict())

        # Use the connection to update the row directly (avoid re-triggering ORM events)
        from sqlalchemy import text as sa_text
        connection.execute(  # type: ignore[attr-defined]
            sa_text("UPDATE users SET name = :name WHERE id = :id"),
            {"name": encrypted_json, "id": target.id},
        )
        # Update the in-memory attribute to match
        target._name_plaintext = encrypted_json  # type: ignore[assignment]
        # PERF-009: Invalidate decryption cache after re-encryption
        target.__dict__.pop("_cached_name", None)
        logger.debug("Re-encrypted name for user %s after INSERT", target.id)
    except Exception:
        logger.critical(
            "SECURITY: Failed to re-encrypt name after INSERT for user %s. "
            "Plaintext name may remain in database. Manual remediation required.",
            target.id,
            exc_info=True,
        )


__all__ = ["User"]
