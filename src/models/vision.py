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

# PERF-009: Sentinel for distinguishing "not cached" from "cached as None"
_SENTINEL = object()


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
        """Get decrypted content (PERF-009: cached after first access)."""
        cached = self.__dict__.get("_cached_content", _SENTINEL)
        if cached is not _SENTINEL:
            return cached  # type: ignore[no-any-return]
        if self._content_plaintext is None:
            self.__dict__["_cached_content"] = None
            return None
        try:
            import json
            data = json.loads(str(self._content_plaintext))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import (
                    EncryptedField,
                    get_encryption_service,
                )
                encrypted = EncryptedField.from_db_dict(data)
                svc = get_encryption_service()
                result = svc.decrypt_field(
                    encrypted, int(self.user_id), "content"
                )
                self.__dict__["_cached_content"] = result
                return result
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        fallback: str | None = str(self._content_plaintext) if self._content_plaintext else None
        self.__dict__["_cached_content"] = fallback
        return fallback

    @content.setter
    def content(self, value: str | None) -> None:
        """Set encrypted content."""
        self.__dict__.pop("_cached_content", None)
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
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Encryption failed for field 'content', refusing to store plaintext",
                extra={"error": type(e).__name__},
            )
            raise ValueError("Cannot store data: encryption service unavailable") from e

    def __repr__(self) -> str:
        return f"<Vision(id={self.id}, user_id={self.user_id}, type={self.type})>"


__all__ = ["Vision"]
