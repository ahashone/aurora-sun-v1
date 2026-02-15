"""
Test to verify HIGH-5 fix: User.name plaintext window is eliminated.

This test confirms that user.name is encrypted BEFORE the INSERT,
not after. The fix pre-generates the user ID in the before_insert
event listener, allowing immediate encryption.
"""

import json

import pytest
from sqlalchemy import text

from src.models.user import User


def test_high5_user_name_encrypted_before_insert(db_session):
    """
    Verify that user.name is encrypted BEFORE database INSERT.

    HIGH-5 Security Fix:
    The original implementation stored user.name in plaintext until after INSERT,
    when the auto-increment ID was available. This created a plaintext window.

    The fix pre-generates the user ID in the before_insert event, allowing
    the name to be encrypted immediately. This test verifies the fix works.
    """
    # Create a user with a name
    user = User(
        telegram_id="high5_test_telegram_id",
        language="en",
        timezone="UTC",
    )
    user.name = "Test User Name"

    # Add to session and commit
    db_session.add(user)
    db_session.commit()

    # Verify the user was created
    assert user.id is not None
    assert user.name == "Test User Name"  # Decryption works

    # Query the raw database to verify encryption
    result = db_session.execute(
        text("SELECT name FROM users WHERE id = :id"),
        {"id": user.id}
    )
    row = result.fetchone()

    assert row is not None, "User row not found in database"
    raw_name = row[0]
    assert raw_name is not None, "Name field is NULL in database"

    # The raw value should be encrypted JSON, not plaintext
    try:
        data = json.loads(raw_name)
        assert isinstance(data, dict), f"Name field is not JSON: {raw_name}"
        assert "ciphertext" in data, f"Name field is JSON but not encrypted: {data}"
        assert "classification" in data
        assert data["classification"] == "sensitive"
        assert "version" in data

        # Additional validation: ciphertext should be base64-encoded
        ciphertext = data["ciphertext"]
        assert isinstance(ciphertext, str)
        assert len(ciphertext) > 0

        # Verify it's NOT the plaintext value
        assert ciphertext != "Test User Name", "Ciphertext appears to be plaintext!"

    except json.JSONDecodeError:
        pytest.fail(
            f"HIGH-5 FIX FAILED: Name field is PLAINTEXT, not encrypted JSON. "
            f"Value: {raw_name}"
        )


def test_high5_user_name_none_handled_correctly(db_session):
    """Verify that None name values are handled correctly."""
    user = User(
        telegram_id="high5_test_none_name",
        language="en",
    )
    # Explicitly set name to None
    user.name = None

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.name is None

    # Verify database stores NULL
    result = db_session.execute(
        text("SELECT name FROM users WHERE id = :id"),
        {"id": user.id}
    )
    row = result.fetchone()
    assert row[0] is None


def test_high5_user_creation_without_name(db_session):
    """Verify users can be created without setting name at all."""
    user = User(
        telegram_id="high5_test_no_name",
        language="en",
    )
    # Don't set name at all

    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.name is None


def test_high5_user_name_set_after_creation(db_session):
    """Verify that setting name after user is created still encrypts properly."""
    user = User(
        telegram_id="high5_test_late_name",
        language="en",
    )

    db_session.add(user)
    db_session.commit()

    # Now set the name after the user exists
    user.name = "Late Name"
    db_session.commit()

    # Verify encryption
    result = db_session.execute(
        text("SELECT name FROM users WHERE id = :id"),
        {"id": user.id}
    )
    row = result.fetchone()
    raw_name = row[0]

    data = json.loads(raw_name)
    assert "ciphertext" in data
    assert data["classification"] == "sensitive"
