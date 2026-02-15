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

from src.lib.encrypted_field import EncryptedFieldDescriptor
from src.lib.encryption import DataClassification
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

    # Encrypted field descriptors (REFACTOR-002: replaces manual property boilerplate)
    # PERF-009: Caching is built into the descriptor
    title = EncryptedFieldDescriptor(
        plaintext_attr="_title_plaintext",
        field_name="title",
        classification=DataClassification.SENSITIVE,
    )
    key_results = EncryptedFieldDescriptor(
        plaintext_attr="_key_results_plaintext",
        field_name="key_results",
        classification=DataClassification.SENSITIVE,
    )

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

    def __repr__(self) -> str:
        return (
            f"<Goal(id={self.id}, user_id={self.user_id},"
            f" type={self.type}, status={self.status})>"
        )


__all__ = ["Goal"]
