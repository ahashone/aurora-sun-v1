"""
Vision Model for Aurora Sun V1.

Data Classification: ART.9_SPECIAL (life vision contains sensitive personal data)

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
    _content_plaintext = Column("content", Text, nullable=True)  # Encrypted storage

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
        Index("idx_vision_user_type", "user_id", "type"),
        Index("idx_vision_created_at", "created_at"),
    )

    @property
    def content(self) -> str | None:
        """Get decrypted content."""
        if self._content_plaintext is None:
            return None
        try:
            import json
            data = json.loads(str(self._content_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import EncryptedField, get_encryption_service
                encrypted = EncryptedField.from_db_dict(data)
                return get_encryption_service().decrypt_field(encrypted, int(self.user_id), "content")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return str(self._content_plaintext) if self._content_plaintext else None

    @content.setter
    def content(self, value: str | None) -> None:
        """Set encrypted content."""
        if value is None:
            setattr(self, '_content_plaintext', None)
            return
        try:
            import json
            from src.lib.encryption import DataClassification, get_encryption_service
            encrypted = get_encryption_service().encrypt_field(
                value, int(self.user_id), DataClassification.ART_9_SPECIAL, "content"
            )
            setattr(self, '_content_plaintext', json.dumps(encrypted.to_db_dict()))
        except Exception:
            setattr(self, '_content_plaintext', value)

    def __repr__(self) -> str:
        return f"<Vision(id={self.id}, user_id={self.user_id}, type={self.type})>"


__all__ = ["Vision"]
