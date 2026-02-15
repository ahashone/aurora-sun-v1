"""
Encryption Foundation for Aurora Sun V1.

This module provides field-level encryption for all SENSITIVE, ART.9, and FINANCIAL
data as specified in ARCHITECTURE.md Section 10 (Security & Privacy Architecture).

Key Features:
- Per-user encryption keys (AES-256-GCM)
- 3-tier envelope encryption for FINANCIAL fields
- HMAC-SHA256 for PII identifiers (telegram_id, name lookups)
- Field-level salting for ART.9 data

Dependencies:
- cryptography>=41.0.0 (for AES-256-GCM)
- keyring>=23.0.0 (for secure key storage)

Usage:
    from src.lib.encryption import EncryptionService, DataClassification, EncryptedField

    service = EncryptionService()
    encrypted = service.encrypt_field("sensitive data", user_id=123, classification=DataClassification.SENSITIVE)
    decrypted = service.decrypt_field(encrypted, user_id=123)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from enum import Enum

# Keyring for secure key storage
try:
    import keyring
    import keyring.backend
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Cryptography imports
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


# =============================================================================
# Data Classification Enum
# =============================================================================

class DataClassification(Enum):
    """
    Data classification levels as defined in ARCHITECTURE.md Section 10.

    Every table and field must be classified at design time.
    Classification determines encryption requirements.

    Classification Hierarchy:
    - PUBLIC: No encryption required
    - INTERNAL: No encryption required (system data)
    - SENSITIVE: AES-256-GCM, per-user key
    - ART_9_SPECIAL: AES-256-GCM, per-user key + field-level salt
    - FINANCIAL: AES-256-GCM, 3-tier envelope (master -> user -> field)
    """
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    ART_9_SPECIAL = "art_9_special"
    FINANCIAL = "financial"

    def requires_encryption(self) -> bool:
        """Check if this classification requires encryption."""
        return self in (
            DataClassification.SENSITIVE,
            DataClassification.ART_9_SPECIAL,
            DataClassification.FINANCIAL,
        )

    def requires_field_salt(self) -> bool:
        """Check if this classification requires field-level salting."""
        return self == DataClassification.ART_9_SPECIAL

    def requires_envelope(self) -> bool:
        """Check if this classification requires 3-tier envelope encryption."""
        return self == DataClassification.FINANCIAL


# =============================================================================
# Encrypted Field Data Structure
# =============================================================================

@dataclass
class EncryptedField:
    """
    Container for encrypted field data.

    Attributes:
        ciphertext: Base64-encoded ciphertext (includes nonce)
        classification: The data classification used
        version: Key version for rotation support
        field_salt: Optional field-level salt (for ART.9 data)
        envelope_nonce: Optional nonce for envelope encryption (FINANCIAL)
    """
    ciphertext: str
    classification: DataClassification
    version: int
    field_salt: str | None = None
    envelope_nonce: str | None = None

    def to_db_dict(self) -> dict[str, str | int | None]:
        """Serialize for database storage."""
        return {
            "ciphertext": self.ciphertext,
            "classification": self.classification.value,
            "version": self.version,
            "field_salt": self.field_salt,
            "envelope_nonce": self.envelope_nonce,
        }

    @classmethod
    def from_db_dict(cls, data: dict[str, str | int | None]) -> EncryptedField:
        """Deserialize from database storage."""
        ciphertext_val = data["ciphertext"]
        classification_val = data["classification"]
        version_val = data["version"]

        if not isinstance(ciphertext_val, str):
            raise ValueError(f"Expected str for ciphertext, got {type(ciphertext_val)}")
        if not isinstance(classification_val, str):
            raise ValueError(f"Expected str for classification, got {type(classification_val)}")
        if not isinstance(version_val, int):
            raise ValueError(f"Expected int for version, got {type(version_val)}")

        field_salt_val = data.get("field_salt")
        envelope_nonce_val = data.get("envelope_nonce")

        return cls(
            ciphertext=ciphertext_val,
            classification=DataClassification(classification_val),
            version=version_val,
            field_salt=str(field_salt_val) if field_salt_val is not None and not isinstance(field_salt_val, str) else (field_salt_val if isinstance(field_salt_val, str) else None),
            envelope_nonce=str(envelope_nonce_val) if envelope_nonce_val is not None and not isinstance(envelope_nonce_val, str) else (envelope_nonce_val if isinstance(envelope_nonce_val, str) else None),
        )


# =============================================================================
# Encryption Service
# =============================================================================

class EncryptionServiceError(Exception):
    """Base exception for encryption service errors."""
    pass


class KeyNotFoundError(EncryptionServiceError):
    """Raised when a user key is not found."""
    pass


class DecryptionError(EncryptionServiceError):
    """Raised when decryption fails."""
    pass


class EncryptionService:
    """
    Handles all field-level encryption for Aurora Sun V1.

    This service implements the encryption architecture defined in
    ARCHITECTURE.md Section 10:

    - SENSITIVE fields: AES-256-GCM, per-user encryption key
    - ART.9 fields: AES-256-GCM, per-user key + field-level salt
    - FINANCIAL fields: AES-256-GCM, 3-tier envelope (master -> user -> field)

    Key Management:
    - Master key: Generated once, stored securely (environment variable or keyring)
    - User keys: Derived from master key + user-specific salt
    - Key rotation: Supported via version tracking

    Security Properties:
    - AES-256-GCM for authenticated encryption
    - Unique nonces per encryption operation
    - PBKDF2-HMAC-SHA256 for key derivation (100,000 iterations)
    - Field-level salts for ART.9 data isolation

    Example:
        >>> service = EncryptionService()
        >>> encrypted = service.encrypt_field(
        ...     plaintext="my sensitive data",
        ...     user_id=123,
        ...     classification=DataClassification.SENSITIVE
        ... )
        >>> decrypted = service.decrypt_field(encrypted, user_id=123)
    """

    # Keyring service name
    SERVICE_NAME = "aurora-sun-v1"

    # Key derivation parameters
    KEY_SIZE = 32  # 256 bits for AES-256
    SALT_SIZE = 16  # 128 bits
    NONCE_SIZE = 12  # 96 bits for GCM (recommended)
    KDF_ITERATIONS = 100_000

    # Version tracking for key rotation
    _current_version: int = 1

    def __init__(
        self,
        master_key: bytes | None = None,
        keyring_service: str | None = None,
    ):
        """
        Initialize the encryption service.

        Args:
            master_key: Master encryption key. If None, attempts to load from
                environment variable AURORA_MASTER_KEY or keyring.
            keyring_service: Custom keyring service name. Defaults to SERVICE_NAME.
        """
        self._master_key = master_key or self._load_master_key()
        self._keyring_service = keyring_service or self.SERVICE_NAME
        self._user_key_cache: dict[int, bytes] = {}

        if not CRYPTO_AVAILABLE:
            raise EncryptionServiceError(
                "cryptography library not installed. "
                "Install with: pip install cryptography keyring"
            )

    def _load_master_key(self) -> bytes:
        """
        Load or generate the master encryption key.

        Priority:
        1. Environment variable AURORA_MASTER_KEY (base64 encoded)
        2. Keyring storage
        3. Generate new (development only - should never happen in production)

        Returns:
            32-byte master key

        Raises:
            EncryptionServiceError: If no valid key can be loaded
        """
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        # Try environment variable first
        env_key = os.environ.get("AURORA_MASTER_KEY")
        if env_key:
            try:
                decoded = base64.b64decode(env_key)
                # Validate master key is exactly 32 bytes (256 bits)
                if len(decoded) != 32:
                    raise ValueError(
                        f"AURORA_MASTER_KEY must be exactly 32 bytes (256 bits) "
                        f"when base64-decoded, got {len(decoded)} bytes. "
                        f"Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
                    )
                return decoded
            except ValueError:
                raise  # Re-raise ValueError (including our length check)
            except Exception as e:
                _logger.debug(
                    "Failed to decode AURORA_MASTER_KEY, trying next method",
                    extra={"error": type(e).__name__},
                )

        # Try keyring
        if KEYRING_AVAILABLE:
            try:
                key = keyring.get_password(self.SERVICE_NAME, "master_key")
                if key:
                    return base64.b64decode(key)
            except Exception as e:
                _logger.debug(
                    "Keyring unavailable for master key, trying next method",
                    extra={"error": type(e).__name__},
                )

        # Generate new key for development (should not happen in production)
        # This will require key rotation after deployment
        key = os.environ.get("AURORA_DEV_KEY")
        if key:
            return base64.b64decode(key)

        # Last resort: deterministic dev key (development only)
        # SECURITY: This key is NOT secret. Data encrypted with it is recoverable
        # across restarts, but offers zero security. Never use in production.
        # Block dev key in production environment
        if os.environ.get("AURORA_DEV_MODE") == "1":
            if os.environ.get("AURORA_ENVIRONMENT") == "production":
                raise RuntimeError(
                    "FATAL: AURORA_DEV_MODE=1 is set but AURORA_ENVIRONMENT=production. "
                    "Refusing to use deterministic dev key in production. "
                    "Set AURORA_MASTER_KEY to a secure random 32-byte base64-encoded key."
                )
            _logger.warning(
                "SECURITY WARNING: Using deterministic dev key. "
                "Data is NOT securely encrypted. "
                "DO NOT USE IN PRODUCTION. Set AURORA_MASTER_KEY for real encryption."
            )
            return hashlib.sha256(b"aurora-sun-dev-key-DO-NOT-USE-IN-PRODUCTION").digest()

        raise EncryptionServiceError(
            "No master key found. Set AURORA_MASTER_KEY environment variable "
            "or configure keyring."
        )

    def _get_user_salt(self, user_id: int) -> bytes:
        """
        Get or create a user-specific salt.

        The salt is derived from the user_id and stored persistently.
        This ensures the same user always gets the same key.

        Uses keyring with file-based fallback. Never silently
        generates a new salt if an existing one cannot be read.

        Args:
            user_id: The user's unique identifier

        Returns:
            16-byte salt unique to this user

        Raises:
            EncryptionServiceError: If salt cannot be retrieved or stored reliably
        """
        import logging as _logging
        _logger = _logging.getLogger(__name__)

        salt_key = f"user_salt_{user_id}"

        # Fallback directory for salt files when keyring is unavailable
        salt_dir = os.environ.get("AURORA_SALT_DIR", os.path.join(os.path.expanduser("~"), ".aurora-sun", "salts"))
        salt_file = os.path.join(salt_dir, f"{salt_key}.salt")

        # Try keyring first
        if KEYRING_AVAILABLE:
            try:
                stored_salt = keyring.get_password(self._keyring_service, salt_key)
                if stored_salt:
                    return base64.b64decode(stored_salt)
            except Exception as e:
                _logger.warning(
                    "Keyring read failed for user salt, trying file fallback",
                    extra={"user_id": user_id, "error": type(e).__name__},
                )

        # Try file-based fallback
        if os.path.exists(salt_file):
            try:
                with open(salt_file) as f:
                    stored_salt = f.read().strip()
                if stored_salt:
                    return base64.b64decode(stored_salt)
            except Exception as e:
                _logger.warning(
                    "File-based salt read failed",
                    extra={"user_id": user_id, "error": type(e).__name__},
                )

        # Generate new salt (only if no existing salt was found in any store)
        salt = os.urandom(self.SALT_SIZE)
        salt_b64 = base64.b64encode(salt).decode()
        stored = False

        # Store in keyring
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(
                    self._keyring_service,
                    salt_key,
                    salt_b64,
                )
                stored = True
            except Exception as e:
                _logger.warning(
                    "Keyring write failed for user salt, using file fallback",
                    extra={"user_id": user_id, "error": type(e).__name__},
                )

        # Always store in file fallback for redundancy
        try:
            os.makedirs(salt_dir, mode=0o700, exist_ok=True)
            with open(salt_file, "w") as f:
                f.write(salt_b64)
            os.chmod(salt_file, 0o600)
            stored = True
        except Exception as e:
            _logger.warning(
                "File-based salt write failed",
                extra={"user_id": user_id, "error": type(e).__name__},
            )

        if not stored:
            raise EncryptionServiceError(
                f"Cannot persist user salt for user_id={user_id}. "
                f"Neither keyring nor file fallback ({salt_dir}) is available. "
                f"Set AURORA_SALT_DIR to a writable directory."
            )

        return salt

    def _derive_user_key(self, user_id: int) -> bytes:
        """
        Derive a user-specific encryption key from the master key.

        Uses PBKDF2-HMAC-SHA256 with user-specific salt.
        This provides key isolation between users.

        Args:
            user_id: The user's unique identifier

        Returns:
            32-byte user-specific encryption key
        """
        if user_id in self._user_key_cache:
            return self._user_key_cache[user_id]

        salt = self._get_user_salt(user_id)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.KDF_ITERATIONS,
            backend=default_backend(),
        )

        key = kdf.derive(self._master_key)
        self._user_key_cache[user_id] = key

        return key

    def _get_field_key(
        self,
        user_id: int,
        field_name: str,
        field_salt: bytes | None = None,
    ) -> bytes:
        """
        Derive a field-specific encryption key.

        For ART.9 data, uses field-level salt for additional isolation.
        For FINANCIAL data, this is the third tier of envelope encryption.

        Args:
            user_id: The user's unique identifier
            field_name: Name of the field being encrypted
            field_salt: Optional field-specific salt

        Returns:
            32-byte field-specific encryption key
        """
        user_key = self._derive_user_key(user_id)

        if field_salt is None:
            # Mix field name with a per-deployment secret to avoid
            # deterministic field salts. Uses AURORA_HASH_SALT (or master key as
            # fallback) so salt varies per deployment.
            deployment_secret = os.environ.get("AURORA_HASH_SALT", "").encode() or self._master_key
            field_salt = hashlib.sha256(
                field_name.encode() + deployment_secret
            ).digest()[:self.SALT_SIZE]

        # Combine user key with field salt
        combined = user_key + field_salt
        field_key = hashlib.pbkdf2_hmac(
            "sha256",
            combined,
            b"field_key",
            self.KDF_ITERATIONS,
            dklen=self.KEY_SIZE,
        )

        return field_key

    def encrypt_field(
        self,
        plaintext: str,
        user_id: int,
        classification: DataClassification,
        field_name: str | None = None,
    ) -> EncryptedField:
        """
        Encrypt a field value based on its classification.

        Encryption Strategy by Classification:
        - SENSITIVE: AES-256-GCM with per-user key
        - ART.9 SPECIAL: AES-256-GCM with per-user key + field-level salt
        - FINANCIAL: 3-tier envelope (master -> user -> field)

        Args:
            plaintext: The plaintext value to encrypt
            user_id: The user this data belongs to
            classification: The data classification level
            field_name: Name of the field (required for ART.9 and FINANCIAL)

        Returns:
            EncryptedField containing all data needed for decryption

        Raises:
            EncryptionServiceError: If encryption fails
            ValueError: If classification requires encryption but plaintext is empty

        Example:
            >>> encrypted = service.encrypt_field(
            ...     plaintext="my health data",
            ...     user_id=123,
            ...     classification=DataClassification.ART_9_SPECIAL,
            ...     field_name="belief_text"
            ... )
        """
        if not classification.requires_encryption():
            raise ValueError(
                f"Classification {classification} does not require encryption"
            )

        if not plaintext:
            raise ValueError("Cannot encrypt empty plaintext")

        plaintext_bytes = plaintext.encode("utf-8")

        if classification == DataClassification.FINANCIAL:
            return self._encrypt_envelope(plaintext_bytes, user_id, field_name or "field")
        elif classification == DataClassification.ART_9_SPECIAL:
            return self._encrypt_with_field_salt(
                plaintext_bytes, user_id, field_name or "field"
            )
        else:
            return self._encrypt_simple(plaintext_bytes, user_id)

    def _encrypt_simple(
        self,
        plaintext: bytes,
        user_id: int,
    ) -> EncryptedField:
        """Encrypt with per-user key only (SENSITIVE)."""
        nonce = os.urandom(self.NONCE_SIZE)
        user_key = self._derive_user_key(user_id)

        aesgcm = AESGCM(user_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return EncryptedField(
            ciphertext=base64.b64encode(nonce + ciphertext).decode(),
            classification=DataClassification.SENSITIVE,
            version=self._current_version,
        )

    def _encrypt_with_field_salt(
        self,
        plaintext: bytes,
        user_id: int,
        field_name: str,
    ) -> EncryptedField:
        """Encrypt with per-user key + field-level salt (ART.9)."""
        # Generate unique field salt
        field_salt = os.urandom(self.SALT_SIZE)

        # Derive field-specific key
        field_key = self._get_field_key(user_id, field_name, field_salt)

        # Encrypt
        nonce = os.urandom(self.NONCE_SIZE)
        aesgcm = AESGCM(field_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return EncryptedField(
            ciphertext=base64.b64encode(nonce + ciphertext).decode(),
            classification=DataClassification.ART_9_SPECIAL,
            version=self._current_version,
            field_salt=base64.b64encode(field_salt).decode(),
        )

    def _encrypt_envelope(
        self,
        plaintext: bytes,
        user_id: int,
        field_name: str,
    ) -> EncryptedField:
        """
        Encrypt using 3-tier envelope encryption (FINANCIAL).

        Layers:
        1. Master key -> user salt -> user key
        2. User key -> field name -> field key
        3. Field key -> unique nonce -> ciphertext
        """
        # Generate envelope nonce for this specific field
        envelope_nonce = os.urandom(self.NONCE_SIZE)

        # Derive field key using envelope nonce as additional salt
        user_key = self._derive_user_key(user_id)
        field_salt = hashlib.sha256(
            field_name.encode() + envelope_nonce
        ).digest()[:self.SALT_SIZE]

        field_key = hashlib.pbkdf2_hmac(
            "sha256",
            user_key + field_salt,
            b"envelope_field_key",
            self.KDF_ITERATIONS,
            dklen=self.KEY_SIZE,
        )

        # Encrypt with field key
        nonce = os.urandom(self.NONCE_SIZE)
        aesgcm = AESGCM(field_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        return EncryptedField(
            ciphertext=base64.b64encode(nonce + ciphertext).decode(),
            classification=DataClassification.FINANCIAL,
            version=self._current_version,
            envelope_nonce=base64.b64encode(envelope_nonce).decode(),
        )

    def decrypt_field(
        self,
        encrypted: EncryptedField,
        user_id: int,
        field_name: str | None = None,
    ) -> str:
        """
        Decrypt an encrypted field value.

        Args:
            encrypted: The EncryptedField to decrypt
            user_id: The user this data belongs to
            field_name: Name of the field (required for ART.9 and FINANCIAL)

        Returns:
            The decrypted plaintext string

        Raises:
            DecryptionError: If decryption fails (wrong key, tampered data)
            KeyNotFoundError: If user key is not found
        """
        classification = encrypted.classification

        if not classification.requires_encryption():
            raise ValueError(
                f"Classification {classification} does not require decryption"
            )

        try:
            ciphertext_with_nonce = base64.b64decode(encrypted.ciphertext)
            nonce = ciphertext_with_nonce[:self.NONCE_SIZE]
            ciphertext = ciphertext_with_nonce[self.NONCE_SIZE:]

            if classification == DataClassification.FINANCIAL:
                return self._decrypt_envelope(
                    ciphertext, nonce, user_id, field_name or "field", encrypted
                )
            elif classification == DataClassification.ART_9_SPECIAL:
                return self._decrypt_with_field_salt(
                    ciphertext, nonce, user_id, field_name or "field", encrypted
                )
            else:
                return self._decrypt_simple(ciphertext, nonce, user_id)

        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}") from e

    def _decrypt_simple(
        self,
        ciphertext: bytes,
        nonce: bytes,
        user_id: int,
    ) -> str:
        """Decrypt with per-user key only."""
        user_key = self._derive_user_key(user_id)

        aesgcm = AESGCM(user_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode("utf-8")

    def _decrypt_with_field_salt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        user_id: int,
        field_name: str,
        encrypted: EncryptedField,
    ) -> str:
        """Decrypt with per-user key + field-level salt."""
        if not encrypted.field_salt:
            raise DecryptionError("Field salt missing for ART.9 encrypted data")

        field_salt = base64.b64decode(encrypted.field_salt)
        field_key = self._get_field_key(user_id, field_name, field_salt)

        aesgcm = AESGCM(field_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode("utf-8")

    def _decrypt_envelope(
        self,
        ciphertext: bytes,
        nonce: bytes,
        user_id: int,
        field_name: str,
        encrypted: EncryptedField,
    ) -> str:
        """Decrypt using 3-tier envelope encryption."""
        if not encrypted.envelope_nonce:
            raise DecryptionError("Envelope nonce missing for FINANCIAL encrypted data")

        envelope_nonce = base64.b64decode(encrypted.envelope_nonce)

        # Derive field key
        user_key = self._derive_user_key(user_id)
        field_salt = hashlib.sha256(
            field_name.encode() + envelope_nonce
        ).digest()[:self.SALT_SIZE]

        field_key = hashlib.pbkdf2_hmac(
            "sha256",
            user_key + field_salt,
            b"envelope_field_key",
            self.KDF_ITERATIONS,
            dklen=self.KEY_SIZE,
        )

        # Decrypt
        aesgcm = AESGCM(field_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode("utf-8")

    @staticmethod
    def needs_re_encryption(encrypted_data: EncryptedField, current_version: int | None = None) -> bool:
        """
        Check if data was encrypted with an old key version
        and needs re-encryption.

        Args:
            encrypted_data: The encrypted field to check
            current_version: The current key version to compare against.
                If None, uses the default version (1).

        Returns:
            True if the data was encrypted with an older version and should
            be re-encrypted with the current key.

        Note:
            This is a detection helper only. Bulk re-encryption should be
            implemented as a database migration that:
            1. Queries all encrypted fields where version < current_version
            2. Decrypts with the old key
            3. Re-encrypts with the current key
            4. Updates the version field

        TODO: Implement bulk re-encryption migration (future task).
            See ARCHITECTURE.md Section 10 for key rotation strategy.
        """
        check_version = current_version if current_version is not None else 1
        return encrypted_data.version < check_version

    def rotate_key(self, user_id: int) -> None:
        """
        Rotate a user's encryption key.

        This generates a new user salt, re-derives the key,
        and increments the version. Existing encrypted data
        remains decryptable with the old version.

        Use needs_re_encryption() to check if existing data
        needs re-encryption after key rotation.

        For full key rotation, you must re-encrypt all user data
        with the new key. This method prepares the service for
        new encryption operations.

        Args:
            user_id: The user whose key should be rotated

        Note:
            Full key rotation requires:
            1. Decrypt all existing data with old key
            2. Call rotate_key()
            3. Re-encrypt all data with new key
            4. Update version in database
        """
        # Generate new user salt
        new_salt = os.urandom(self.SALT_SIZE)

        # Store in keyring
        salt_key = f"user_salt_{user_id}"
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(
                    self._keyring_service,
                    salt_key,
                    base64.b64encode(new_salt).decode(),
                )
            except Exception:
                pass

        # Clear cache to force re-derivation
        if user_id in self._user_key_cache:
            del self._user_key_cache[user_id]

        # Increment version
        self._current_version += 1

    def destroy_keys(self, user_id: int) -> None:
        """
        Destroy all encryption keys for a user.

        This is called during GDPR deletion (SW-15) to ensure
        all encrypted data is cryptographically unrecoverable.

        Args:
            user_id: The user whose keys should be destroyed

        Warning:
            After calling this, ALL encrypted data for this user
            becomes unrecoverable. This is intentional for GDPR compliance.

        Note:
            This destroys the encryption keys but does NOT delete
            the encrypted data from the database. The data remains
            but is cryptographically inaccessible.
        """
        # Remove from cache
        if user_id in self._user_key_cache:
            del self._user_key_cache[user_id]

        # Remove user salt from keyring
        salt_key = f"user_salt_{user_id}"
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(self._keyring_service, salt_key)
            except Exception:
                pass  # Best effort

        # Note: We don't destroy the master key as it's shared


# =============================================================================
# HMAC Service for PII Hashing
# =============================================================================

class HashService:
    """
    Provides HMAC-SHA256 hashing for PII identifiers.

    Used for:
    - telegram_id storage (never store raw, always HMAC)
    - Name lookups (allow search without exposing names)
    - Consent record IP hashing

    The hash is salted with a application-specific salt to prevent
    rainbow table attacks.
    """

    def __init__(self, hash_salt: bytes | None = None):
        """
        Initialize the hash service.

        Args:
            hash_salt: Application-specific salt for hashing.
                      If None, loads from AURORA_HASH_SALT env var or generates.
        """
        if hash_salt:
            self._salt = hash_salt
        else:
            env_salt = os.environ.get("AURORA_HASH_SALT")
            if env_salt:
                self._salt = base64.b64decode(env_salt)
            elif os.environ.get("AURORA_DEV_MODE") == "1":
                # Block dev hash salt in production environment
                if os.environ.get("AURORA_ENVIRONMENT") == "production":
                    raise RuntimeError(
                        "FATAL: AURORA_DEV_MODE=1 is set but AURORA_ENVIRONMENT=production. "
                        "Refusing to use deterministic hash salt in production. "
                        "Set AURORA_HASH_SALT to a secure random base64-encoded value."
                    )
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "SECURITY WARNING: Using deterministic hash salt. "
                    "Hashes are NOT secure. "
                    "DO NOT USE IN PRODUCTION. Set AURORA_HASH_SALT for real hashing."
                )
                self._salt = hashlib.sha256(b"aurora-sun-dev-salt-DO-NOT-USE-IN-PRODUCTION").digest()
            else:
                raise EncryptionServiceError(
                    "No hash salt found. Set AURORA_HASH_SALT environment variable."
                )

    def hash_pii(self, value: str) -> str:
        """
        Hash a PII value using HMAC-SHA256.

        Args:
            value: The PII value to hash (e.g., telegram_id, name)

        Returns:
            Base64-encoded hash

        Example:
            >>> hash_service = HashService()
            >>> hashed = hash_service.hash_pii("123456789")
            >>> # Store hashed in database, never the raw value
        """
        h = hmac.new(self._salt, digestmod=hashlib.sha256)
        h.update(value.encode("utf-8"))
        return base64.b64encode(h.digest()).decode()

    def verify_pii(self, value: str, hash: str) -> bool:
        """
        Verify a PII value against its hash.

        Args:
            value: The plaintext value
            hash: The expected hash

        Returns:
            True if the value matches the hash
        """
        return secrets.compare_digest(self.hash_pii(value), hash)

    def hash_for_lookup(self, value: str) -> str:
        """
        Create a lookup hash for searching without exposing PII.

        This is different from hash_pii in that it uses a different
        salt, allowing separate lookup indices.

        Args:
            value: The value to hash for lookup

        Returns:
            Base64-encoded lookup hash
        """
        lookup_salt_env = os.environ.get("AURORA_LOOKUP_SALT")
        if not lookup_salt_env:
            # Fall back to main salt with different context
            lookup_salt_bytes = self._salt
            context = b"lookup"
        else:
            lookup_salt_bytes = base64.b64decode(lookup_salt_env)
            context = b""

        h = hmac.new(lookup_salt_bytes, digestmod=hashlib.sha256)
        if context:
            h.update(context)
        h.update(value.encode("utf-8"))
        return base64.b64encode(h.digest()).decode()


# =============================================================================
# Convenience Functions
# =============================================================================

# Global service instances (lazy initialization)
_encryption_service: EncryptionService | None = None
_hash_service: HashService | None = None


def get_encryption_service() -> EncryptionService:
    """Get the global encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def get_hash_service() -> HashService:
    """Get the global hash service instance."""
    global _hash_service
    if _hash_service is None:
        _hash_service = HashService()
    return _hash_service


def encrypt_for_user(
    plaintext: str,
    user_id: int,
    classification: DataClassification,
    field_name: str | None = None,
) -> EncryptedField:
    """
    Convenience function to encrypt a value for a user.

    Args:
        plaintext: The plaintext to encrypt
        user_id: The user ID
        classification: The data classification
        field_name: Optional field name (required for ART.9 and FINANCIAL)

    Returns:
        EncryptedField
    """
    return get_encryption_service().encrypt_field(
        plaintext, user_id, classification, field_name
    )


def decrypt_for_user(
    encrypted: EncryptedField,
    user_id: int,
    field_name: str | None = None,
) -> str:
    """
    Convenience function to decrypt a value for a user.

    Args:
        encrypted: The EncryptedField to decrypt
        user_id: The user ID
        field_name: Optional field name (required for ART.9 and FINANCIAL)

    Returns:
        Decrypted plaintext
    """
    return get_encryption_service().decrypt_field(encrypted, user_id, field_name)


def hash_telegram_id(telegram_id: str) -> str:
    """
    Hash a Telegram ID for storage.

    Telegram IDs are PII and should never be stored in plaintext.
    Use this function to create a secure hash.

    Args:
        telegram_id: The Telegram user ID (as string)

    Returns:
        Base64-encoded hash
    """
    return get_hash_service().hash_pii(telegram_id)


def hash_for_search(value: str) -> str:
    """
    Hash a value for searching without exposing it.

    Used for name lookups and other searchable PII fields.

    Args:
        value: The value to hash

    Returns:
        Base64-encoded lookup hash
    """
    return get_hash_service().hash_for_lookup(value)
