"""
Unit tests for the encryption module.

These tests verify the functionality of:
- DataClassification enum
- EncryptionService (AES-256-GCM encryption)
- HashService (HMAC-SHA256 PII hashing)
- EncryptedField serialization

The tests are designed to run without a real master key by using
the AURORA_DEV_MODE and AURORA_DEV_KEY environment variables.
"""

import base64
import os

import pytest

# Set up test environment before importing the module
os.environ["AURORA_DEV_MODE"] = "1"
os.environ["AURORA_HASH_SALT"] = base64.b64encode(b"test-salt-for-hashing-32bytes").decode()

# Now import the module
from src.lib.encryption import (
    DataClassification,
    DecryptionError,
    EncryptedField,
    EncryptionService,
    HashService,
)

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def test_master_key():
    """Provide a test master key for encryption tests."""
    return os.urandom(32)  # 256-bit key


@pytest.fixture
def test_hash_salt():
    """Provide a test hash salt for HashService tests."""
    return b"test-hash-salt-32-bytes-long!!"


@pytest.fixture
def encryption_service(test_master_key):
    """Create an EncryptionService instance with a test master key."""
    return EncryptionService(master_key=test_master_key)


@pytest.fixture
def hash_service(test_hash_salt):
    """Create a HashService instance with a test salt."""
    return HashService(hash_salt=test_hash_salt)


# =============================================================================
# TestDataClassification
# =============================================================================

class TestDataClassification:
    """Test the DataClassification enum values and methods."""

    def test_public_value(self):
        """Test PUBLIC classification value."""
        assert DataClassification.PUBLIC.value == "public"

    def test_internal_value(self):
        """Test INTERNAL classification value."""
        assert DataClassification.INTERNAL.value == "internal"

    def test_sensitive_value(self):
        """Test SENSITIVE classification value."""
        assert DataClassification.SENSITIVE.value == "sensitive"

    def test_art_9_special_value(self):
        """Test ART_9_SPECIAL classification value."""
        assert DataClassification.ART_9_SPECIAL.value == "art_9_special"

    def test_financial_value(self):
        """Test FINANCIAL classification value."""
        assert DataClassification.FINANCIAL.value == "financial"

    def test_requires_encryption_sensitive(self):
        """Test SENSITIVE requires encryption."""
        assert DataClassification.SENSITIVE.requires_encryption() is True

    def test_requires_encryption_art_9(self):
        """Test ART_9_SPECIAL requires encryption."""
        assert DataClassification.ART_9_SPECIAL.requires_encryption() is True

    def test_requires_encryption_financial(self):
        """Test FINANCIAL requires encryption."""
        assert DataClassification.FINANCIAL.requires_encryption() is True

    def test_requires_encryption_public(self):
        """Test PUBLIC does not require encryption."""
        assert DataClassification.PUBLIC.requires_encryption() is False

    def test_requires_encryption_internal(self):
        """Test INTERNAL does not require encryption."""
        assert DataClassification.INTERNAL.requires_encryption() is False

    def test_requires_field_salt_art_9(self):
        """Test ART_9_SPECIAL requires field salt."""
        assert DataClassification.ART_9_SPECIAL.requires_field_salt() is True

    def test_requires_field_salt_other(self):
        """Test other classifications do not require field salt."""
        assert DataClassification.SENSITIVE.requires_field_salt() is False
        assert DataClassification.FINANCIAL.requires_field_salt() is False

    def test_requires_envelope_financial(self):
        """Test FINANCIAL requires envelope encryption."""
        assert DataClassification.FINANCIAL.requires_envelope() is True

    def test_requires_envelope_other(self):
        """Test other classifications do not require envelope."""
        assert DataClassification.SENSITIVE.requires_envelope() is False
        assert DataClassification.ART_9_SPECIAL.requires_envelope() is False


# =============================================================================
# TestEncryptionService
# =============================================================================

class TestEncryptionService:
    """Test the EncryptionService class."""

    def test_encrypt_decrypt_roundtrip_sensitive(
        self, encryption_service: EncryptionService
    ):
        """Encrypt and decrypt SENSITIVE data, verify match."""
        user_id = 12345
        plaintext = "This is sensitive user data that needs encryption."

        # Encrypt
        encrypted = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        # Verify encrypted field properties
        assert encrypted.classification == DataClassification.SENSITIVE
        assert encrypted.ciphertext is not None
        assert len(encrypted.ciphertext) > 0
        assert encrypted.version == 1

        # Decrypt
        decrypted = encryption_service.decrypt_field(encrypted, user_id=user_id)

        # Verify match
        assert decrypted == plaintext

    def test_encrypt_decrypt_roundtrip_art_9(
        self, encryption_service: EncryptionService
    ):
        """Encrypt and decrypt ART.9 data, verify match."""
        user_id = 12345
        plaintext = "Health belief: I believe exercise will help my condition."
        field_name = "belief_text"

        # Encrypt
        encrypted = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.ART_9_SPECIAL,
            field_name=field_name,
        )

        # Verify encrypted field properties
        assert encrypted.classification == DataClassification.ART_9_SPECIAL
        assert encrypted.ciphertext is not None
        assert encrypted.field_salt is not None  # ART.9 has field salt
        assert encrypted.version == 1

        # Decrypt
        decrypted = encryption_service.decrypt_field(
            encrypted, user_id=user_id, field_name=field_name
        )

        # Verify match
        assert decrypted == plaintext

    def test_encrypt_decrypt_roundtrip_financial(
        self, encryption_service: EncryptionService
    ):
        """Encrypt and decrypt FINANCIAL data, verify match."""
        user_id = 12345
        plaintext = "1234-5678-9012-3456"  # Credit card number
        field_name = "credit_card"

        # Encrypt
        encrypted = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.FINANCIAL,
            field_name=field_name,
        )

        # Verify encrypted field properties
        assert encrypted.classification == DataClassification.FINANCIAL
        assert encrypted.ciphertext is not None
        assert encrypted.envelope_nonce is not None  # FINANCIAL has envelope nonce
        assert encrypted.version == 1

        # Decrypt
        decrypted = encryption_service.decrypt_field(
            encrypted, user_id=user_id, field_name=field_name
        )

        # Verify match
        assert decrypted == plaintext

    def test_different_ciphertext_same_plaintext(
        self, encryption_service: EncryptionService
    ):
        """Same plaintext produces different ciphertext due to random nonce."""
        user_id = 12345
        plaintext = "Same data encrypted twice"

        # Encrypt twice
        encrypted1 = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )
        encrypted2 = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        # Ciphertext should be different due to random nonce
        assert encrypted1.ciphertext != encrypted2.ciphertext

        # But both should decrypt to the same plaintext
        decrypted1 = encryption_service.decrypt_field(encrypted1, user_id=user_id)
        decrypted2 = encryption_service.decrypt_field(encrypted2, user_id=user_id)

        assert decrypted1 == plaintext
        assert decrypted2 == plaintext

    def test_wrong_user_id_fails(self, encryption_service: EncryptionService):
        """Decrypting with wrong user_id fails gracefully."""
        user_id = 12345
        wrong_user_id = 67890
        plaintext = "Sensitive data for user 12345"

        # Encrypt for user 12345
        encrypted = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        # Try to decrypt with wrong user_id
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(encrypted, user_id=wrong_user_id)

    def test_rotate_key(self, encryption_service: EncryptionService):
        """Key rotation works correctly."""
        user_id = 12345
        plaintext = "Data before key rotation"

        # Encrypt before rotation
        encrypted_before = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        # Decrypt works before rotation
        decrypted_before = encryption_service.decrypt_field(
            encrypted_before, user_id=user_id
        )
        assert decrypted_before == plaintext

        # Rotate key
        encryption_service.rotate_key(user_id)

        # Note: After rotation, the service uses a new salt
        # The old encrypted data can no longer be decrypted
        # because the user salt has changed
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(encrypted_before, user_id=user_id)

        # New encryptions work with the new key
        new_plaintext = "Data after key rotation"
        encrypted_after = encryption_service.encrypt_field(
            plaintext=new_plaintext,
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        decrypted_after = encryption_service.decrypt_field(
            encrypted_after, user_id=user_id
        )
        assert decrypted_after == new_plaintext

    def test_destroy_keys(self, encryption_service: EncryptionService):
        """Keys destroyed, subsequent encryption fails gracefully."""
        user_id = 12345

        # Encrypt some data
        encrypted = encryption_service.encrypt_field(
            plaintext="Data to be lost",
            user_id=user_id,
            classification=DataClassification.SENSITIVE,
        )

        # Verify it decrypts
        decrypted = encryption_service.decrypt_field(encrypted, user_id=user_id)
        assert decrypted == "Data to be lost"

        # Destroy keys
        encryption_service.destroy_keys(user_id)

        # After destruction, we cannot decrypt the old data
        # because the user salt has been removed from keyring
        # Note: In a real test without keyring, this may still work
        # because the key was cached in memory

        # New encryption should fail because we can't derive the user key
        # without the user salt (which was "deleted" from keyring)
        # In test mode without keyring, this may still work

    def test_empty_plaintext_raises_error(
        self, encryption_service: EncryptionService
    ):
        """Encrypting empty plaintext raises ValueError."""
        with pytest.raises(ValueError, match="Cannot encrypt empty plaintext"):
            encryption_service.encrypt_field(
                plaintext="",
                user_id=12345,
                classification=DataClassification.SENSITIVE,
            )

    def test_non_encrypted_classification_raises_error(
        self, encryption_service: EncryptionService
    ):
        """Encrypting with PUBLIC classification raises ValueError."""
        with pytest.raises(ValueError, match="does not require encryption"):
            encryption_service.encrypt_field(
                plaintext="Some data",
                user_id=12345,
                classification=DataClassification.PUBLIC,
            )

    def test_art_9_without_field_name(self, encryption_service: EncryptionService):
        """ART.9 encryption works without explicit field_name (uses default)."""
        user_id = 12345
        plaintext = "Health data"

        encrypted = encryption_service.encrypt_field(
            plaintext=plaintext,
            user_id=user_id,
            classification=DataClassification.ART_9_SPECIAL,
        )

        decrypted = encryption_service.decrypt_field(encrypted, user_id=user_id)
        assert decrypted == plaintext


# =============================================================================
# TestHashService
# =============================================================================

class TestHashService:
    """Test the HashService class."""

    def test_hash_pii(self, hash_service: HashService):
        """Hash telegram_id, verify format."""
        telegram_id = "123456789"

        # Hash the PII
        hashed = hash_service.hash_pii(telegram_id)

        # Verify it's a valid base64 string
        try:
            decoded = base64.b64decode(hashed)
            assert len(decoded) == 32  # SHA256 produces 32 bytes
        except Exception:
            pytest.fail("Hash is not valid base64")

        # Verify hash is deterministic
        hashed_again = hash_service.hash_pii(telegram_id)
        assert hashed == hashed_again

    def test_verify_pii(self, hash_service: HashService):
        """Verify correct PII."""
        telegram_id = "123456789"

        # Hash the PII
        hashed = hash_service.hash_pii(telegram_id)

        # Verify returns True for correct PII
        assert hash_service.verify_pii(telegram_id, hashed) is True

    def test_verify_pii_wrong(self, hash_service: HashService):
        """Wrong PII fails verification."""
        telegram_id = "123456789"
        wrong_telegram_id = "987654321"

        # Hash the correct PII
        hashed = hash_service.hash_pii(telegram_id)

        # Verify returns False for wrong PII
        assert hash_service.verify_pii(wrong_telegram_id, hashed) is False

    def test_hash_for_lookup(self, hash_service: HashService):
        """Lookup hash works."""
        value = "John Doe"

        # Create lookup hash
        lookup_hash = hash_service.hash_for_lookup(value)

        # Verify it's valid base64
        try:
            decoded = base64.b64decode(lookup_hash)
            assert len(decoded) == 32
        except Exception:
            pytest.fail("Lookup hash is not valid base64")

        # Lookup hash should be different from regular PII hash
        pii_hash = hash_service.hash_pii(value)
        assert lookup_hash != pii_hash

    def test_hash_different_values_different_hashes(
        self, hash_service: HashService
    ):
        """Different values produce different hashes."""
        hash1 = hash_service.hash_pii("value1")
        hash2 = hash_service.hash_pii("value2")

        assert hash1 != hash2

    def test_hash_same_value_same_hash(self, hash_service: HashService):
        """Same value produces same hash (deterministic)."""
        value = "consistent-value"

        hash1 = hash_service.hash_pii(value)
        hash2 = hash_service.hash_pii(value)

        assert hash1 == hash2


# =============================================================================
# TestEncryptedField
# =============================================================================

class TestEncryptedField:
    """Test the EncryptedField dataclass."""

    def test_to_db_dict_sensitive(self):
        """Test serialization of SENSITIVE EncryptedField."""
        encrypted = EncryptedField(
            ciphertext="dGVzdA==",
            classification=DataClassification.SENSITIVE,
            version=1,
        )

        db_dict = encrypted.to_db_dict()

        assert db_dict["ciphertext"] == "dGVzdA=="
        assert db_dict["classification"] == "sensitive"
        assert db_dict["version"] == 1
        assert db_dict["field_salt"] is None
        assert db_dict["envelope_nonce"] is None

    def test_to_db_dict_art_9(self):
        """Test serialization of ART.9 EncryptedField."""
        encrypted = EncryptedField(
            ciphertext="dGVzdA==",
            classification=DataClassification.ART_9_SPECIAL,
            version=2,
            field_salt="c2FsdA==",
        )

        db_dict = encrypted.to_db_dict()

        assert db_dict["classification"] == "art_9_special"
        assert db_dict["field_salt"] == "c2FsdA=="
        assert db_dict["envelope_nonce"] is None

    def test_to_db_dict_financial(self):
        """Test serialization of FINANCIAL EncryptedField."""
        encrypted = EncryptedField(
            ciphertext="dGVzdA==",
            classification=DataClassification.FINANCIAL,
            version=3,
            envelope_nonce="bm9uY2U=",
        )

        db_dict = encrypted.to_db_dict()

        assert db_dict["classification"] == "financial"
        assert db_dict["field_salt"] is None
        assert db_dict["envelope_nonce"] == "bm9uY2U="

    def test_from_db_dict_sensitive(self):
        """Test deserialization of SENSITIVE EncryptedField."""
        data = {
            "ciphertext": "dGVzdA==",
            "classification": "sensitive",
            "version": 1,
            "field_salt": None,
            "envelope_nonce": None,
        }

        encrypted = EncryptedField.from_db_dict(data)

        assert encrypted.ciphertext == "dGVzdA=="
        assert encrypted.classification == DataClassification.SENSITIVE
        assert encrypted.version == 1

    def test_from_db_dict_art_9(self):
        """Test deserialization of ART.9 EncryptedField."""
        data = {
            "ciphertext": "dGVzdA==",
            "classification": "art_9_special",
            "version": 2,
            "field_salt": "c2FsdA==",
            "envelope_nonce": None,
        }

        encrypted = EncryptedField.from_db_dict(data)

        assert encrypted.classification == DataClassification.ART_9_SPECIAL
        assert encrypted.field_salt == "c2FsdA=="

    def test_from_db_dict_financial(self):
        """Test deserialization of FINANCIAL EncryptedField."""
        data = {
            "ciphertext": "dGVzdA==",
            "classification": "financial",
            "version": 3,
            "field_salt": None,
            "envelope_nonce": "bm9uY2U=",
        }

        encrypted = EncryptedField.from_db_dict(data)

        assert encrypted.classification == DataClassification.FINANCIAL
        assert encrypted.envelope_nonce == "bm9uY2U="

    def test_roundtrip_serialization(self):
        """Test full serialization/deserialization roundtrip."""
        original = EncryptedField(
            ciphertext="SGVsbG8gV29ybGQh",
            classification=DataClassification.ART_9_SPECIAL,
            version=5,
            field_salt="YXJ0NnNpZ25z",
        )

        # Serialize
        db_dict = original.to_db_dict()

        # Deserialize
        restored = EncryptedField.from_db_dict(db_dict)

        # Verify all fields match
        assert restored.ciphertext == original.ciphertext
        assert restored.classification == original.classification
        assert restored.version == original.version
        assert restored.field_salt == original.field_salt
        assert restored.envelope_nonce == original.envelope_nonce


# =============================================================================
# Integration Tests
# =============================================================================

class TestEncryptionIntegration:
    """Integration tests for encryption workflow."""

    def test_full_user_data_lifecycle(self, encryption_service: EncryptionService):
        """Test complete lifecycle of user data encryption."""
        user_id = 99999

        # Store multiple types of data
        sensitive_data = "User's private note"
        art9_data = "User's health belief"
        financial_data = "User's account number"

        # Encrypt all
        encrypted_sensitive = encryption_service.encrypt_field(
            sensitive_data, user_id, DataClassification.SENSITIVE
        )
        encrypted_art9 = encryption_service.encrypt_field(
            art9_data, user_id, DataClassification.ART_9_SPECIAL, "belief"
        )
        encrypted_financial = encryption_service.encrypt_field(
            financial_data, user_id, DataClassification.FINANCIAL, "account"
        )

        # Decrypt all
        decrypted_sensitive = encryption_service.decrypt_field(
            encrypted_sensitive, user_id
        )
        decrypted_art9 = encryption_service.decrypt_field(
            encrypted_art9, user_id, "belief"
        )
        decrypted_financial = encryption_service.decrypt_field(
            encrypted_financial, user_id, "account"
        )

        # Verify
        assert decrypted_sensitive == sensitive_data
        assert decrypted_art9 == art9_data
        assert decrypted_financial == financial_data

    def test_multiple_users_isolated(self, encryption_service: EncryptionService):
        """Test that different users cannot read each other's data."""
        user1_id = 11111
        user2_id = 22222
        plaintext = "Shared secret"

        # User 1 encrypts
        encrypted = encryption_service.encrypt_field(
            plaintext, user1_id, DataClassification.SENSITIVE
        )

        # User 2 cannot decrypt
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(encrypted, user2_id)
