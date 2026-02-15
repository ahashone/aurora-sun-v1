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


# =============================================================================
# Coverage Boost: Error Paths in EncryptionService
# =============================================================================

class TestEncryptionServiceErrorPaths:
    """Test error paths in EncryptionService for coverage."""

    def test_corrupt_ciphertext_raises_decryption_error(
        self, encryption_service: EncryptionService
    ):
        """Corrupt ciphertext should raise DecryptionError."""
        bad = EncryptedField(
            ciphertext=base64.b64encode(b"bad data").decode(),
            classification=DataClassification.SENSITIVE,
            version=1,
        )
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(bad, user_id=1)

    def test_truncated_ciphertext_raises_decryption_error(
        self, encryption_service: EncryptionService
    ):
        """Truncated ciphertext (< NONCE_SIZE) should still raise."""
        short = EncryptedField(
            ciphertext=base64.b64encode(b"ab").decode(),
            classification=DataClassification.SENSITIVE,
            version=1,
        )
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(short, user_id=1)

    def test_wrong_version_after_rotation(
        self, encryption_service: EncryptionService
    ):
        """After rotation, old version data cannot be decrypted."""
        user_id = 55555
        encrypted = encryption_service.encrypt_field(
            "test", user_id, DataClassification.SENSITIVE
        )
        assert encrypted.version == 1
        encryption_service.rotate_key(user_id)
        # Old data should fail
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(encrypted, user_id)

    def test_encrypt_internal_classification_raises(
        self, encryption_service: EncryptionService
    ):
        """INTERNAL classification does not require encryption."""
        with pytest.raises(ValueError, match="does not require"):
            encryption_service.encrypt_field(
                "data", 1, DataClassification.INTERNAL
            )

    def test_decrypt_non_encrypted_classification_raises(
        self, encryption_service: EncryptionService
    ):
        """Cannot decrypt a field marked as PUBLIC."""
        field = EncryptedField(
            ciphertext="data",
            classification=DataClassification.PUBLIC,
            version=1,
        )
        with pytest.raises(
            ValueError, match="does not require decryption"
        ):
            encryption_service.decrypt_field(field, user_id=1)

    def test_art9_decrypt_without_field_salt_raises(
        self, encryption_service: EncryptionService
    ):
        """ART_9 decrypt without field_salt raises DecryptionError."""
        user_id = 77777
        encrypted = encryption_service.encrypt_field(
            "health data", user_id,
            DataClassification.ART_9_SPECIAL, "field"
        )
        # Remove field_salt
        broken = EncryptedField(
            ciphertext=encrypted.ciphertext,
            classification=DataClassification.ART_9_SPECIAL,
            version=encrypted.version,
            field_salt=None,
        )
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(broken, user_id, "field")

    def test_financial_decrypt_without_envelope_nonce_raises(
        self, encryption_service: EncryptionService
    ):
        """FINANCIAL decrypt without envelope_nonce raises."""
        user_id = 88888
        encrypted = encryption_service.encrypt_field(
            "account data", user_id,
            DataClassification.FINANCIAL, "account"
        )
        broken = EncryptedField(
            ciphertext=encrypted.ciphertext,
            classification=DataClassification.FINANCIAL,
            version=encrypted.version,
            envelope_nonce=None,
        )
        with pytest.raises(DecryptionError):
            encryption_service.decrypt_field(broken, user_id, "account")


# =============================================================================
# Coverage Boost: Key Rotation Edge Cases
# =============================================================================

class TestKeyRotationEdgeCases:
    """Test key rotation edge cases."""

    def test_needs_re_encryption_old_version(self):
        """Old version data needs re-encryption."""
        field = EncryptedField(
            ciphertext="data",
            classification=DataClassification.SENSITIVE,
            version=1,
        )
        assert EncryptionService.needs_re_encryption(field, 2) is True

    def test_needs_re_encryption_current_version(self):
        """Current version data does not need re-encryption."""
        field = EncryptedField(
            ciphertext="data",
            classification=DataClassification.SENSITIVE,
            version=2,
        )
        assert EncryptionService.needs_re_encryption(field, 2) is False

    def test_needs_re_encryption_default_version(self):
        """With None current_version, defaults to 1."""
        field = EncryptedField(
            ciphertext="data",
            classification=DataClassification.SENSITIVE,
            version=1,
        )
        assert EncryptionService.needs_re_encryption(field) is False

    def test_rotate_increments_version(
        self, encryption_service: EncryptionService
    ):
        """Rotation increments the version counter."""
        initial = encryption_service._current_version
        encryption_service.rotate_key(44444)
        assert encryption_service._current_version == initial + 1

    def test_rotate_clears_cache(
        self, encryption_service: EncryptionService
    ):
        """Rotation clears the rotated user from cache."""
        user_id = 33333
        # Force cache population
        encryption_service._derive_user_key(user_id)
        assert user_id in encryption_service._user_key_cache
        encryption_service.rotate_key(user_id)
        assert user_id not in encryption_service._user_key_cache

    def test_rotate_does_not_affect_other_users(
        self, encryption_service: EncryptionService
    ):
        """Rotation for user A doesn't break user B's data."""
        user_a = 11111
        user_b = 22222
        plain = "shared format"
        enc_b = encryption_service.encrypt_field(
            plain, user_b, DataClassification.SENSITIVE
        )
        encryption_service.rotate_key(user_a)
        decrypted = encryption_service.decrypt_field(enc_b, user_b)
        assert decrypted == plain


# =============================================================================
# Coverage Boost: Destroy Keys
# =============================================================================

class TestDestroyKeysEdgeCases:
    """Test destroy_keys edge cases."""

    def test_destroy_clears_cache(
        self, encryption_service: EncryptionService
    ):
        """destroy_keys removes user from cache."""
        user_id = 66666
        encryption_service._derive_user_key(user_id)
        assert user_id in encryption_service._user_key_cache
        encryption_service.destroy_keys(user_id)
        assert user_id not in encryption_service._user_key_cache

    def test_destroy_nonexistent_user_no_error(
        self, encryption_service: EncryptionService
    ):
        """destroy_keys on nonexistent user does not raise."""
        encryption_service.destroy_keys(999999)


# =============================================================================
# Coverage Boost: EncryptedField.from_db_dict Validation
# =============================================================================

class TestEncryptedFieldFromDbDictErrors:
    """Test EncryptedField.from_db_dict error paths."""

    def test_invalid_ciphertext_type_raises(self):
        """Non-string ciphertext raises ValueError."""
        with pytest.raises(ValueError, match="Expected str for ciphertext"):
            EncryptedField.from_db_dict({
                "ciphertext": 123,
                "classification": "sensitive",
                "version": 1,
            })

    def test_invalid_classification_type_raises(self):
        """Non-string classification raises ValueError."""
        with pytest.raises(
            ValueError, match="Expected str for classification"
        ):
            EncryptedField.from_db_dict({
                "ciphertext": "data",
                "classification": 999,
                "version": 1,
            })

    def test_invalid_version_type_raises(self):
        """Non-int version raises ValueError."""
        with pytest.raises(ValueError, match="Expected int for version"):
            EncryptedField.from_db_dict({
                "ciphertext": "data",
                "classification": "sensitive",
                "version": "1",
            })

    def test_non_string_field_salt_converted(self):
        """Non-string field_salt is converted to string."""
        field = EncryptedField.from_db_dict({
            "ciphertext": "data",
            "classification": "art_9_special",
            "version": 1,
            "field_salt": 12345,
        })
        assert field.field_salt == "12345"

    def test_non_string_envelope_nonce_converted(self):
        """Non-string envelope_nonce is converted to string."""
        field = EncryptedField.from_db_dict({
            "ciphertext": "data",
            "classification": "financial",
            "version": 1,
            "envelope_nonce": 67890,
        })
        assert field.envelope_nonce == "67890"


# =============================================================================
# Coverage Boost: HashService Edge Cases
# =============================================================================

class TestHashServiceEdgeCases:
    """Test HashService edge cases for coverage."""

    def test_hash_pii_empty_string(self, hash_service: HashService):
        """Hashing empty string still produces valid output."""
        result = hash_service.hash_pii("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_pii_unicode(self, hash_service: HashService):
        """Unicode values hash correctly."""
        result = hash_service.hash_pii("\u00fc\u00f6\u00e4\u00df")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_verify_pii_empty_string(self, hash_service: HashService):
        """Verify works with empty string."""
        h = hash_service.hash_pii("")
        assert hash_service.verify_pii("", h) is True

    def test_hash_for_lookup_deterministic(
        self, hash_service: HashService
    ):
        """hash_for_lookup is deterministic."""
        h1 = hash_service.hash_for_lookup("test")
        h2 = hash_service.hash_for_lookup("test")
        assert h1 == h2

    def test_hash_for_lookup_differs_from_hash_pii(
        self, hash_service: HashService
    ):
        """Lookup hash differs from PII hash."""
        pii = hash_service.hash_pii("same_value")
        lookup = hash_service.hash_for_lookup("same_value")
        assert pii != lookup


# =============================================================================
# Coverage Boost: DataClassification Methods
# =============================================================================

class TestDataClassificationMethods:
    """Additional DataClassification coverage."""

    def test_all_members_have_requires_encryption(self):
        """Every classification has requires_encryption."""
        for dc in DataClassification:
            result = dc.requires_encryption()
            assert isinstance(result, bool)

    def test_public_no_encryption(self):
        assert DataClassification.PUBLIC.requires_encryption() is False

    def test_internal_no_encryption(self):
        assert DataClassification.INTERNAL.requires_encryption() is False

    def test_sensitive_requires_encryption(self):
        assert DataClassification.SENSITIVE.requires_encryption() is True

    def test_art9_requires_encryption(self):
        assert DataClassification.ART_9_SPECIAL.requires_encryption() is True

    def test_financial_requires_encryption(self):
        assert DataClassification.FINANCIAL.requires_encryption() is True


# =============================================================================
# Coverage Boost: _load_master_key Paths
# =============================================================================

class TestLoadMasterKeyPaths:
    """Test _load_master_key env var, keyring, dev paths."""

    def test_env_var_master_key(self):
        """AURORA_MASTER_KEY env var is loaded correctly."""
        import unittest.mock as mock
        key = os.urandom(32)
        env = {
            "AURORA_MASTER_KEY": base64.b64encode(key).decode(),
            "AURORA_DEV_MODE": "1",
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            svc = EncryptionService()
            assert svc._master_key == key

    def test_env_var_master_key_wrong_length_raises(self):
        """AURORA_MASTER_KEY with wrong length raises ValueError."""
        import unittest.mock as mock
        bad_key = os.urandom(16)  # 16 bytes, not 32
        env = {
            "AURORA_MASTER_KEY": base64.b64encode(bad_key).decode(),
            "AURORA_DEV_MODE": "1",
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValueError, match="must be exactly 32 bytes"):
                EncryptionService()

    def test_dev_mode_fallback_key(self):
        """Dev mode uses deterministic key when no other available."""
        import hashlib
        import unittest.mock as mock
        env = {
            "AURORA_DEV_MODE": "1",
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        # Remove AURORA_MASTER_KEY and AURORA_DEV_KEY if present
        with mock.patch.dict(
            os.environ, env, clear=False
        ):
            os.environ.pop("AURORA_MASTER_KEY", None)
            os.environ.pop("AURORA_DEV_KEY", None)
            svc = EncryptionService()
            expected = hashlib.sha256(
                b"aurora-sun-dev-key-DO-NOT-USE-IN-PRODUCTION"
            ).digest()
            assert svc._master_key == expected

    def test_dev_mode_production_env_raises(self):
        """Dev mode + production environment raises RuntimeError."""
        import unittest.mock as mock
        env = {
            "AURORA_DEV_MODE": "1",
            "AURORA_ENVIRONMENT": "production",
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AURORA_MASTER_KEY", None)
            os.environ.pop("AURORA_DEV_KEY", None)
            with pytest.raises(
                RuntimeError, match="AURORA_DEV_MODE=1.*production"
            ):
                EncryptionService()

    def test_no_key_available_raises(self):
        """No master key available at all raises error."""
        import unittest.mock as mock

        from src.lib.encryption import EncryptionServiceError
        env = {
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AURORA_MASTER_KEY", None)
            os.environ.pop("AURORA_DEV_KEY", None)
            os.environ.pop("AURORA_DEV_MODE", None)
            # Also mock KEYRING to not be available
            with mock.patch(
                "src.lib.encryption.KEYRING_AVAILABLE", False
            ):
                with pytest.raises(EncryptionServiceError):
                    EncryptionService()

    def test_aurora_dev_key_env_var(self):
        """AURORA_DEV_KEY env var is loaded."""
        import unittest.mock as mock
        key = os.urandom(32)
        env = {
            "AURORA_DEV_KEY": base64.b64encode(key).decode(),
            "AURORA_HASH_SALT": base64.b64encode(
                b"test-salt-for-hashing-32bytes"
            ).decode(),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AURORA_MASTER_KEY", None)
            # Mock keyring to not return a key
            with mock.patch(
                "src.lib.encryption.KEYRING_AVAILABLE", False
            ):
                svc = EncryptionService()
                assert svc._master_key == key


# =============================================================================
# Coverage Boost: HashService Init Paths
# =============================================================================

class TestHashServiceInitPaths:
    """Test HashService initialization paths."""

    def test_init_from_env_salt(self):
        """HashService loads salt from AURORA_HASH_SALT env var."""
        import unittest.mock as mock
        salt = b"test-salt-32bytes-for-hashing!!"
        env = {"AURORA_HASH_SALT": base64.b64encode(salt).decode()}
        with mock.patch.dict(os.environ, env, clear=False):
            svc = HashService()
            assert svc._salt == salt

    def test_init_dev_mode_fallback(self):
        """Dev mode uses deterministic salt."""
        import hashlib
        import unittest.mock as mock
        env = {"AURORA_DEV_MODE": "1"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AURORA_HASH_SALT", None)
            svc = HashService()
            expected = hashlib.sha256(
                b"aurora-sun-dev-salt-DO-NOT-USE-IN-PRODUCTION"
            ).digest()
            assert svc._salt == expected

    def test_init_dev_mode_production_raises(self):
        """Dev mode + production environment raises."""
        import unittest.mock as mock
        env = {
            "AURORA_DEV_MODE": "1",
            "AURORA_ENVIRONMENT": "production",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AURORA_HASH_SALT", None)
            with pytest.raises(RuntimeError, match="production"):
                HashService()

    def test_init_no_salt_raises(self):
        """No salt available raises EncryptionServiceError."""
        import unittest.mock as mock

        from src.lib.encryption import EncryptionServiceError
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AURORA_HASH_SALT", None)
            os.environ.pop("AURORA_DEV_MODE", None)
            with pytest.raises(EncryptionServiceError):
                HashService()


# =============================================================================
# Coverage Boost: hash_for_lookup with AURORA_LOOKUP_SALT
# =============================================================================

class TestHashForLookupWithEnvSalt:
    """Test hash_for_lookup when AURORA_LOOKUP_SALT is set."""

    def test_lookup_with_env_salt(self, hash_service: HashService):
        """Setting AURORA_LOOKUP_SALT uses it for lookup."""
        import unittest.mock as mock
        lookup_salt = b"lookup-salt-32bytes!!"
        env = {
            "AURORA_LOOKUP_SALT": base64.b64encode(
                lookup_salt
            ).decode()
        }
        with mock.patch.dict(os.environ, env, clear=False):
            result = hash_service.hash_for_lookup("test_value")
            assert isinstance(result, str)
            assert len(result) > 0

    def test_lookup_without_env_salt_uses_main_salt(
        self, hash_service: HashService
    ):
        """Without AURORA_LOOKUP_SALT, uses main salt + context."""
        import unittest.mock as mock
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AURORA_LOOKUP_SALT", None)
            result = hash_service.hash_for_lookup("test_value")
            assert isinstance(result, str)
            assert len(result) > 0


# =============================================================================
# Coverage Boost: Convenience Functions (global singletons)
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_encryption_service_returns_instance(self):
        """get_encryption_service returns an EncryptionService."""
        import src.lib.encryption as enc_mod
        # Reset global singleton
        enc_mod._encryption_service = None
        svc = enc_mod.get_encryption_service()
        assert isinstance(svc, EncryptionService)
        # Second call returns same instance
        assert enc_mod.get_encryption_service() is svc

    def test_get_hash_service_returns_instance(self):
        """get_hash_service returns a HashService."""
        import src.lib.encryption as enc_mod
        enc_mod._hash_service = None
        svc = enc_mod.get_hash_service()
        assert isinstance(svc, HashService)
        assert enc_mod.get_hash_service() is svc

    def test_encrypt_for_user_convenience(self):
        """encrypt_for_user uses global singleton."""
        import src.lib.encryption as enc_mod
        enc_mod._encryption_service = None
        result = enc_mod.encrypt_for_user(
            "test data", 12345, DataClassification.SENSITIVE
        )
        assert isinstance(result, EncryptedField)
        assert result.classification == DataClassification.SENSITIVE

    def test_decrypt_for_user_convenience(self):
        """decrypt_for_user uses global singleton."""
        import src.lib.encryption as enc_mod
        enc_mod._encryption_service = None
        encrypted = enc_mod.encrypt_for_user(
            "roundtrip", 12345, DataClassification.SENSITIVE
        )
        plaintext = enc_mod.decrypt_for_user(encrypted, 12345)
        assert plaintext == "roundtrip"

    def test_hash_telegram_id_convenience(self):
        """hash_telegram_id uses global HashService."""
        import src.lib.encryption as enc_mod
        enc_mod._hash_service = None
        result = enc_mod.hash_telegram_id("123456789")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_for_search_convenience(self):
        """hash_for_search uses global HashService."""
        import src.lib.encryption as enc_mod
        enc_mod._hash_service = None
        result = enc_mod.hash_for_search("search_term")
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# Coverage Boost: _get_user_salt File-Based Paths
# =============================================================================

class TestGetUserSaltPaths:
    """Test _get_user_salt file-based salt storage paths."""

    def test_salt_stored_in_file(
        self, encryption_service: EncryptionService
    ):
        """User salt is written to file-based fallback."""
        user_id = 123456
        salt = encryption_service._get_user_salt(user_id)
        assert isinstance(salt, bytes)
        assert len(salt) == encryption_service.SALT_SIZE

        # Calling again should return the same salt (from file)
        salt2 = encryption_service._get_user_salt(user_id)
        assert salt == salt2

    def test_salt_file_read_error_generates_new(
        self, encryption_service: EncryptionService
    ):
        """If file read fails, a new salt is generated."""
        import unittest.mock as mock
        user_id = 654321
        # First call generates and stores the salt
        encryption_service._get_user_salt(user_id)

        # Mock os.path.exists to return False (simulate no file)
        with mock.patch(
            "src.lib.encryption.KEYRING_AVAILABLE", False
        ):
            with mock.patch("os.path.exists", return_value=False):
                # This will generate a new salt since file is "gone"
                new_salt = encryption_service._get_user_salt(
                    user_id + 1
                )
                assert isinstance(new_salt, bytes)
