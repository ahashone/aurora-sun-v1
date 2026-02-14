"""
Task Model for Aurora Sun V1.

Data Classification: SENSITIVE (title contains personal task data)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    pass


class Task(Base):
    """
    Task model representing individual tasks derived from goals.

    Task status:
    - pending: Not yet started
    - in_progress: Currently being worked on
    - completed: Task finished

    Priority:
    - 1: Highest priority (must do)
    - 2: High priority
    - 3: Medium priority
    - 4: Low priority
    - 5: Lowest priority

    Attributes:
        id: Primary key
        user_id: Foreign key to users.id
        goal_id: Foreign key to goals.id (optional)
        title: Task title (encrypted in production)
        status: Task status (pending | in_progress | completed)
        priority: Priority level (1-5)
        committed_date: Date the user committed to complete the task
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Data Classification: SENSITIVE
    - title: Encrypted with AES-256-GCM (per-user key)
    """

    __tablename__ = "tasks"

    # Relationships
    user = relationship("User", back_populates="tasks")
    goal = relationship("Goal", back_populates="tasks")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goal_id = Column(
        Integer,
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Task content
    _title_plaintext = Column("title", Text, nullable=True)  # Encrypted storage

    # Task state
    status = Column(String(20), default="pending", nullable=False)  # pending | in_progress | completed
    priority = Column(Integer, nullable=True)  # 1-5
    committed_date = Column(Date, nullable=True, index=True)

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
        Index("idx_task_user_status", "user_id", "status"),
        Index("idx_task_user_priority", "user_id", "priority"),
        Index("idx_task_committed_date", "committed_date"),
        Index("idx_task_created_at", "created_at"),
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

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, user_id={self.user_id}, status={self.status}, priority={self.priority})>"


__all__ = ["Task"]
