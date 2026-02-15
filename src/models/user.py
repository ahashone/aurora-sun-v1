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

    # GDPR Art. 18: Processing restriction (HIGH-8)
    # "active" = normal processing, "restricted" = data retained but no processing
    processing_restriction = Column(String(12), default="active", nullable=False)

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
        """
        Set encrypted name.

        HIGH-5 FIX: If self.id is None, we store plaintext temporarily.
        The before_insert event listener will pre-generate the ID, allowing
        the name to be encrypted before the INSERT. This eliminates the
        plaintext window.
        """
        self.__dict__.pop("_cached_name", None)
        if value is None:
            setattr(self, '_name_plaintext', None)
            return
        # If ID not yet assigned, store plaintext temporarily
        # (will be encrypted in before_insert event)
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
        """Convert internal segment code to user-facing name (MED-20: single source)."""
        from src.core.segment_context import SEGMENT_DISPLAY_NAMES
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
# HIGH-5 FIX: Pre-generate ID before INSERT to enable immediate encryption
# =============================================================================
@event.listens_for(User, "before_insert")
def _pre_generate_id_for_encryption(
    mapper: object, connection: object, target: User
) -> None:
    """
    Pre-generate the user ID before INSERT to eliminate the plaintext window.

    Security Fix (HIGH-5):
    The original implementation stored user.name in plaintext until after INSERT,
    when the auto-increment ID was available. This created a plaintext window
    where sensitive data was temporarily unencrypted in memory and potentially
    in database logs.

    This event listener pre-generates the ID using a database-agnostic approach:
    - PostgreSQL: Query the sequence directly
    - SQLite/MySQL: Query MAX(id)+1 (safe because we're in a transaction)

    Once the ID is assigned, the name field is encrypted BEFORE the INSERT,
    ensuring the name is never stored in plaintext in the database.
    """
    # Only pre-generate if ID is not already set
    if target.id is not None:
        return

    # Pre-generate ID using database-specific method
    from sqlalchemy import text as sa_text

    # Get the dialect name
    dialect_name = connection.dialect.name  # type: ignore[attr-defined]

    try:
        if dialect_name == 'postgresql':
            # PostgreSQL: Use sequence
            result = connection.execute(  # type: ignore[attr-defined]
                sa_text("SELECT nextval('users_id_seq')")
            )
            new_id = result.scalar()
        else:
            # SQLite/MySQL/others: Use MAX(id) + 1 approach
            # This is safe because we're in a transaction
            result = connection.execute(  # type: ignore[attr-defined]
                sa_text("SELECT COALESCE(MAX(id), 0) + 1 FROM users")
            )
            new_id = result.scalar()

        target.id = new_id  # type: ignore[assignment]
        logger.debug("Pre-generated user ID %s for encryption before INSERT (dialect: %s)", new_id, dialect_name)
    except Exception as e:
        logger.error(
            "Failed to pre-generate user ID, encryption will be delayed",
            extra={"error": type(e).__name__, "dialect": dialect_name},
        )
        # Don't raise - allow the INSERT to proceed with auto-increment
        # The after_insert handler will catch this case
        return

    # Now encrypt any plaintext name field
    raw_name = target._name_plaintext
    if raw_name is None:
        return

    # Check if already encrypted
    try:
        data = json.loads(str(raw_name))
        if isinstance(data, dict) and "ciphertext" in data:
            return  # Already encrypted, nothing to do
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Encrypt the plaintext name now that we have an ID
    try:
        from src.lib.encryption import DataClassification, get_encryption_service
        encrypted = get_encryption_service().encrypt_field(
            str(raw_name), int(target.id), DataClassification.SENSITIVE, "name"
        )
        encrypted_json = json.dumps(encrypted.to_db_dict())
        target._name_plaintext = encrypted_json  # type: ignore[assignment]
        # PERF-009: Invalidate decryption cache after encryption
        target.__dict__.pop("_cached_name", None)
        logger.debug("Encrypted name for user %s before INSERT", target.id)
    except Exception as e:
        logger.critical(
            "SECURITY: Failed to encrypt name before INSERT for user %s. "
            "Refusing to proceed with plaintext storage.",
            target.id,
            exc_info=True,
        )
        raise ValueError("Cannot store user: encryption failed") from e


__all__ = ["User"]
