"""
Goal Model for Aurora Sun V1.

Data Classification: SENSITIVE (title contains personal goal data)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    pass


class Goal(Base):
    """
    Goal model representing user goals derived from their vision.

    Goal types:
    - 90d: 90-day goals (derived from life vision)
    - weekly: Weekly goals
    - daily: Daily goals

    Goal status:
    - active: Currently being worked on
    - completed: Goal achieved
    - archived: No longer relevant

    Attributes:
        id: Primary key
        user_id: Foreign key to users.id
        vision_id: Foreign key to visions.id (optional, for 90d goals)
        type: Goal type (90d | weekly | daily)
        title: Goal title (encrypted in production)
        key_results: JSON string of key results (encrypted in production)
        status: Goal status (active | completed | archived)
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Data Classification: SENSITIVE
    - title: Encrypted with AES-256-GCM (per-user key)
    - key_results: Encrypted JSON
    """

    __tablename__ = "goals"

    # Relationships
    user = relationship("User", back_populates="goals")
    vision = relationship("Vision", back_populates="goals")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vision_id = Column(
        Integer,
        ForeignKey("visions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Goal content
    type = Column(String(10), nullable=False)  # 90d | weekly | daily
    _title_plaintext = Column("title", Text, nullable=True)  # Encrypted storage
    _key_results_plaintext = Column("key_results", Text, nullable=True)  # Encrypted storage
    status = Column(String(20), default="active", nullable=False)  # active | completed | archived

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
        Index("idx_goal_user_type", "user_id", "type"),
        Index("idx_goal_user_status", "user_id", "status"),
        Index("idx_goal_vision_id", "vision_id"),
        Index("idx_goal_created_at", "created_at"),
    )

    @property
    def title(self) -> str | None:
        """Get decrypted title."""
        if self._title_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._title_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "title")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._title_plaintext) if self._title_plaintext else None

    @title.setter
    def title(self, value: str | None) -> None:
        """Set encrypted title."""
        if value is None:
            setattr(self, '_title_plaintext', None)
            return
        try:
            import json
            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "title"
            )
            setattr(self, '_title_plaintext', json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, '_title_plaintext', value)

    @property
    def key_results(self) -> str | None:
        """Get decrypted key results."""
        if self._key_results_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._key_results_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "key_results")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._key_results_plaintext) if self._key_results_plaintext else None

    @key_results.setter
    def key_results(self, value: str | None) -> None:
        """Set encrypted key results."""
        if value is None:
            setattr(self, '_key_results_plaintext', None)
            return
        try:
            import json
            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.SENSITIVE, "key_results"
            )
            setattr(self, '_key_results_plaintext', json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, '_key_results_plaintext', value)

    def __repr__(self) -> str:
        return f"<Goal(id={self.id}, user_id={self.user_id}, type={self.type}, status={self.status})>"


__all__ = ["Goal"]
