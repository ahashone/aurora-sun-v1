"""
Lib package for Aurora Sun V1.

Contains shared utilities:
- encryption.py: Field-level encryption (AES-256-GCM)
- security.py: Input sanitization and rate limiting
- gdpr.py: GDPR compliance utilities
- circuit_breaker.py: Circuit breaker for external service calls
"""

from src.lib.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
    circuit_breaker,
    get_all_circuit_breakers,
    get_circuit_breaker,
)
from src.lib.encryption import (
    DataClassification,
    EncryptedField,
    EncryptionService,
    decrypt_for_user,
    encrypt_for_user,
    get_encryption_service,
    get_hash_service,
    hash_for_search,
    hash_telegram_id,
)
from src.lib.security import (
    InputSanitizer,
    MessageSizeValidator,
    RateLimiter,
    SecurityHeaders,
    sanitize_for_llm,
    sanitize_for_storage,
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    "circuit_breaker",
    "get_circuit_breaker",
    "get_all_circuit_breakers",
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
    "sanitize_for_llm",
    "sanitize_for_storage",
]
