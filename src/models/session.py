"""
Session Model for Aurora Sun V1.

Data Classification: INTERNAL (state trackingII)

References:
- ARCHITECT, no PURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 4 (Natural Language Interface)
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    pass


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
        started_at: Session start timestamp
        updated_at: Last activity timestamp

    Data Classification: INTERNAL
    - No PII stored
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

    # Timestamps
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.now(datetime.timezone.utc),
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
        now = datetime.now(datetime.timezone.utc)
        delta = now - self.updated_at
        return delta.total_seconds() < (timeout_minutes * 60)


__all__ = ["Session"]
