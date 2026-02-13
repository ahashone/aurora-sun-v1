"""
User Model for Aurora Sun V1.

Data Classification: SENSITIVE (telegram_id is hashed, name is encrypted)

References:
- ARCHITECTURE.md Section 14 (Data Models)
- ARCHITECTURE.md Section 10 (Security & Privacy Architecture)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.orm import relationship

from src.models.base import Base


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

    # Columns
    id = Column(Integer, primary_key=True, autoincrement=True)

    # PII - Always hashed, never stored in plaintext
    telegram_id = Column(String(64), unique=True, nullable=False, index=True)

    # User profile
    name = Column(String(255), nullable=True)  # Encrypted in production
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
        Index("idx_user_language", "language"),
        Index("idx_user_working_style", "working_style_code"),
        Index("idx_user_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id_hash={self.telegram_id[:8]}..., language={self.language})>"

    @property
    def segment_display_name(self) -> str:
        """Convert internal segment code to user-facing name."""
        SEGMENT_DISPLAY_NAMES = {
            "AD": "ADHD",
            "AU": "Autism",
            "AH": "AuDHD",
            "NT": "Neurotypical",
            "CU": "Custom",
        }
        return SEGMENT_DISPLAY_NAMES.get(self.working_style_code, "Neurotypical")


__all__ = ["User"]
