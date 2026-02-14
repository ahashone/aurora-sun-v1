"""
Vision Model for Aurora Sun V1.

Data Classification: ART.9_SPECIAL (life vision contains sensitive personal data)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    pass


class Vision(Base):
    """
    Vision model representing a user's life vision or goals.

    Vision types:
    - life: The ideal life description ("What does your ideal life look like?")
    - 10y: 10-year vision
    - 3y: 3-year vision

    Attributes:
        id: Primary key
        user_id: Foreign key to users.id
        type: Vision type (life | 10y | 3y)
        content: The vision text (encrypted in production)
        created_at: Creation timestamp
        updated_at: Last update timestamp

    Data Classification: ART.9_SPECIAL
    - content is encrypted with AES-256-GCM + field-level salt
    """

    __tablename__ = "visions"

    # Relationships
    user = relationship("User", back_populates="visions")
    goals = relationship("Goal", back_populates="vision", cascade="all, delete-orphan")

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Vision content
    type = Column(String(10), nullable=False)  # life | 10y | 3y
    content = Column(Text, nullable=True)  # Encrypted in production

    # Timestamps
    created_at = Column(
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
        Index("idx_vision_user_type", "user_id", "type"),
        Index("idx_vision_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Vision(id={self.id}, user_id={self.user_id}, type={self.type})>"


__all__ = ["Vision"]
