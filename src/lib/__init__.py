"""
Lib package for Aurora Sun V1.

Contains shared utilities:
- encryption.py: Field-level encryption (AES-256-GCM)
- security.py: Input sanitization and rate limiting
- gdpr.py: GDPR compliance utilities
"""

from src.lib.encryption import (
    EncryptionService,
    DataClassification,
    EncryptedField,
    get_encryption_service,
    get_hash_service,
    encrypt_for_user,
    decrypt_for_user,
    hash_telegram_id,
    hash_for_search,
)
from src.lib.security import (
    InputSanitizer,
    RateLimiter,
    MessageSizeValidator,
    SecurityHeaders,
)

__all__ = [
    # Encryption
    "EncryptionService",
    "DataClassification",
    "EncryptedField",
    "get_encryption_service",
    "get_hash_service",
    "encrypt_for_user",
    "decrypt_for_user",
    "hash_telegram_id",
    "hash_for_search",
    # Security
    "InputSanitizer",
    "RateLimiter",
    "MessageSizeValidator",
    "SecurityHeaders",
]
