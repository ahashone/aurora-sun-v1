"""
Encrypted Field Descriptor for Aurora Sun V1.

Provides a reusable descriptor that handles the encrypt/decrypt pattern
for SQLAlchemy model properties. Replaces duplicated property boilerplate
across model files (goal.py, task.py, vision.py, belief.py, etc.).

Usage:
    class Goal(Base):
        _title_plaintext = Column("title", Text, nullable=True)
        title = EncryptedFieldDescriptor(
            plaintext_attr="_title_plaintext",
            field_name="title",
            classification=DataClassification.SENSITIVE,
        )

Features:
- Decrypt on get (with JSON parse + EncryptedField.from_db_dict)
- Encrypt on set (with EncryptionService + JSON serialize)
- PERF-009: Caching after first decryption (cache key per instance)
- Configurable fail behavior: raise on encryption failure vs. fallback to plaintext

Reference:
- REFACTOR-002: Extract encryption property to descriptor
- src/lib/encryption.py: EncryptionService, EncryptedField, DataClassification
"""

from __future__ import annotations

import json
import logging
from typing import Any, overload

from src.lib.encryption import DataClassification

logger = logging.getLogger(__name__)


class EncryptedFieldDescriptor:
    """
    Descriptor that handles transparent encrypt/decrypt for SQLAlchemy model fields.

    Replaces the duplicated property pattern across model files. Each instance
    handles one encrypted field on a model.

    Args:
        plaintext_attr: The name of the underlying SQLAlchemy Column attribute
            (e.g., "_title_plaintext"). This is where the encrypted JSON blob
            is actually stored.
        field_name: The logical field name used for encryption context
            (e.g., "title", "content", "belief_text"). Passed to
            EncryptionService.encrypt_field/decrypt_field.
        classification: Data classification level. Determines encryption
            strength (SENSITIVE, ART_9_SPECIAL, FINANCIAL).
        user_id_attr: Name of the attribute on the model that holds the user ID.
            Defaults to "user_id".
        fail_hard: If True (default), raise ValueError when encryption fails on set.
            If False, fall back to storing plaintext (legacy behavior for older models).

    Example:
        class MyModel(Base):
            _secret_plaintext = Column("secret", Text)
            user_id = Column(Integer)

            secret = EncryptedFieldDescriptor(
                plaintext_attr="_secret_plaintext",
                field_name="secret",
                classification=DataClassification.SENSITIVE,
            )

        # Usage:
        obj.secret = "hello"   # encrypts and stores JSON blob
        obj.secret              # decrypts and returns "hello"
    """

    def __init__(
        self,
        plaintext_attr: str,
        field_name: str,
        classification: DataClassification,
        user_id_attr: str = "user_id",
        fail_hard: bool = True,
    ) -> None:
        self.plaintext_attr = plaintext_attr
        self.field_name = field_name
        self.classification = classification
        self.user_id_attr = user_id_attr
        self.fail_hard = fail_hard
        # Cache key is unique per descriptor instance
        self._cache_key = f"_cached_{field_name}"

    def __set_name__(self, owner: type[Any], name: str) -> None:
        """Called when the descriptor is assigned to a class attribute."""
        self.public_name = name

    @overload
    def __get__(
        self, obj: None, objtype: type[Any] | None = None,
    ) -> EncryptedFieldDescriptor: ...
    @overload
    def __get__(
        self, obj: Any, objtype: type[Any] | None = None,
    ) -> str | None: ...

    def __get__(
        self, obj: Any, objtype: type[Any] | None = None,
    ) -> str | None | EncryptedFieldDescriptor:
        """
        Decrypt and return the field value.

        Uses PERF-009 caching: after first decryption, the result is cached
        in the instance __dict__ to avoid repeated decryption on the same
        access within a session.
        """
        if obj is None:
            # Class-level access (e.g., for SQLAlchemy column introspection)
            return self

        # PERF-009: Check cache first
        _sentinel = object()
        cached = obj.__dict__.get(self._cache_key, _sentinel)
        if cached is not _sentinel:
            cached_value: str | None = cached
            return cached_value

        # Read the raw stored value
        raw_value = getattr(obj, self.plaintext_attr, None)

        if raw_value is None:
            obj.__dict__[self._cache_key] = None
            return None

        # Try to decrypt
        try:
            data = json.loads(str(raw_value))
            if isinstance(data, dict) and "ciphertext" in data:
                from src.lib.encryption import (
                    EncryptedField,
                    get_encryption_service,
                )

                encrypted = EncryptedField.from_db_dict(data)
                svc = get_encryption_service()
                user_id = int(getattr(obj, self.user_id_attr))
                result: str = svc.decrypt_field(
                    encrypted, user_id, self.field_name
                )
                obj.__dict__[self._cache_key] = result
                return result
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

        # Fallback: return raw value as string
        fallback: str | None = str(raw_value) if raw_value else None
        obj.__dict__[self._cache_key] = fallback
        return fallback

    def __set__(self, obj: Any, value: str | None) -> None:
        """
        Encrypt and store the field value.

        Invalidates the cache before writing. If encryption fails:
        - fail_hard=True: raises ValueError (newer models)
        - fail_hard=False: falls back to plaintext storage (legacy models)
        """
        # Invalidate cache
        obj.__dict__.pop(self._cache_key, None)

        if value is None:
            setattr(obj, self.plaintext_attr, None)
            return

        try:
            from src.lib.encryption import get_encryption_service

            svc = get_encryption_service()
            user_id = int(getattr(obj, self.user_id_attr))
            encrypted = svc.encrypt_field(
                value, user_id, self.classification, self.field_name
            )
            setattr(obj, self.plaintext_attr, json.dumps(encrypted.to_db_dict()))
        except Exception as e:
            if self.fail_hard:
                logger.error(
                    "Encryption failed for field '%s', refusing to store plaintext",
                    self.field_name,
                    extra={"error": type(e).__name__},
                )
                raise ValueError(
                    "Cannot store data: encryption service unavailable"
                ) from e
            else:
                # Legacy fallback: store plaintext
                setattr(obj, self.plaintext_attr, value)


__all__ = ["EncryptedFieldDescriptor"]
