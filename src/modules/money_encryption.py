"""
Money Module Encryption Helpers.

Centralizes all encrypt/decrypt operations for FINANCIAL and ART_9_SPECIAL data.
Uses 3-tier envelope encryption via EncryptionService.

Data Classification: FINANCIAL / ART_9_SPECIAL
Reference: ARCHITECTURE.md Section 7 (Money Pillar)
"""

from __future__ import annotations

import json
from typing import Any

from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    EncryptionService,
)


def encrypt_financial(
    value: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Encrypt a financial field value and return JSON string for DB storage.

    Args:
        value: Plaintext value
        user_id: User ID for per-user key derivation
        field_name: Field name for envelope encryption
        encryption: EncryptionService instance

    Returns:
        JSON-serialised EncryptedField dict
    """
    encrypted = encryption.encrypt_field(
        plaintext=value,
        user_id=user_id,
        classification=DataClassification.FINANCIAL,
        field_name=field_name,
    )
    return json.dumps(encrypted.to_db_dict())


def decrypt_financial(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Decrypt a financial field value from its JSON DB representation.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance

    Returns:
        Decrypted plaintext string
    """
    data: dict[str, Any] = json.loads(stored_json)
    encrypted = EncryptedField.from_db_dict(data)
    return encryption.decrypt_field(encrypted, user_id=user_id, field_name=field_name)


def encrypt_art9(
    value: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Encrypt an ART_9_SPECIAL field value and return JSON string for DB storage.

    Args:
        value: Plaintext value
        user_id: User ID
        field_name: Field name for field-level salt
        encryption: EncryptionService instance

    Returns:
        JSON-serialised EncryptedField dict
    """
    encrypted = encryption.encrypt_field(
        plaintext=value,
        user_id=user_id,
        classification=DataClassification.ART_9_SPECIAL,
        field_name=field_name,
    )
    return json.dumps(encrypted.to_db_dict())


def decrypt_art9(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
) -> str:
    """Decrypt an ART_9_SPECIAL field value from its JSON DB representation.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance

    Returns:
        Decrypted plaintext string
    """
    data: dict[str, Any] = json.loads(stored_json)
    encrypted = EncryptedField.from_db_dict(data)
    return encryption.decrypt_field(encrypted, user_id=user_id, field_name=field_name)


def decrypt_or_fallback(
    stored_json: str,
    user_id: int,
    field_name: str,
    encryption: EncryptionService,
    classification: DataClassification = DataClassification.FINANCIAL,
) -> str:
    """Decrypt a field value, falling back to plaintext_fallback if present.

    Centralizes the common decrypt-or-fallback pattern used throughout the module.

    Args:
        stored_json: JSON-serialised EncryptedField dict from DB
        user_id: User ID
        field_name: Field name
        encryption: EncryptionService instance
        classification: Data classification (default: FINANCIAL)

    Returns:
        Decrypted plaintext string, or the plaintext_fallback value

    Raises:
        EncryptionServiceError: If decryption fails and no fallback is available
        json.JSONDecodeError: If stored_json is not valid JSON
        ValueError: If the decrypted value cannot be processed
        KeyError: If required fields are missing
    """
    data: dict[str, Any] = json.loads(stored_json)
    if "plaintext_fallback" in data:
        return str(data["plaintext_fallback"])

    if classification == DataClassification.ART_9_SPECIAL:
        return decrypt_art9(stored_json, user_id, field_name, encryption)
    return decrypt_financial(stored_json, user_id, field_name, encryption)
