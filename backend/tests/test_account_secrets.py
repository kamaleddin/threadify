"""Tests for Account model encrypted token storage."""

import os

import pytest
from app.db.base import Base
from app.db.models import Account
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def db_session(monkeypatch: pytest.MonkeyPatch) -> Session:
    """Create a temporary in-memory SQLite database for testing with encryption key."""
    # Set a test encryption key
    test_key = os.urandom(32)
    import base64

    monkeypatch.setenv("SECRET_AES_KEY", base64.urlsafe_b64encode(test_key).decode("ascii"))

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_account_access_token_encryption(db_session: Session) -> None:
    """Test that access tokens are encrypted when stored."""
    # Create account with access token
    account = Account(handle="@testuser", provider="x")
    account.access_token = "secret_access_token_12345"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Verify ciphertext is stored (not plaintext)
    assert account.token_encrypted is not None
    assert account.token_encrypted.startswith("v1:")
    assert "secret_access_token_12345" not in account.token_encrypted

    # Verify we can read back the plaintext
    assert account.access_token == "secret_access_token_12345"


def test_account_refresh_token_encryption(db_session: Session) -> None:
    """Test that refresh tokens are encrypted when stored."""
    # Create account with refresh token
    account = Account(handle="@refreshuser", provider="x")
    account.refresh_token = "secret_refresh_token_67890"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Verify ciphertext is stored (not plaintext)
    assert account.refresh_encrypted is not None
    assert account.refresh_encrypted.startswith("v1:")
    assert "secret_refresh_token_67890" not in account.refresh_encrypted

    # Verify we can read back the plaintext
    assert account.refresh_token == "secret_refresh_token_67890"


def test_account_both_tokens_encryption(db_session: Session) -> None:
    """Test that both tokens can be encrypted simultaneously."""
    account = Account(handle="@bothuser", provider="x")
    account.access_token = "access_abc123"
    account.refresh_token = "refresh_xyz789"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Both are encrypted
    assert account.token_encrypted is not None
    assert account.refresh_encrypted is not None
    assert account.token_encrypted.startswith("v1:")
    assert account.refresh_encrypted.startswith("v1:")

    # Both can be decrypted
    assert account.access_token == "access_abc123"
    assert account.refresh_token == "refresh_xyz789"


def test_account_null_tokens(db_session: Session) -> None:
    """Test that None tokens work correctly."""
    account = Account(handle="@nulluser", provider="x")
    account.access_token = None
    account.refresh_token = None

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # No encrypted data stored
    assert account.token_encrypted is None
    assert account.refresh_encrypted is None

    # Properties return None
    assert account.access_token is None
    assert account.refresh_token is None


def test_account_update_token(db_session: Session) -> None:
    """Test that updating tokens works correctly."""
    account = Account(handle="@updateuser", provider="x")
    account.access_token = "original_token"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    original_encrypted = account.token_encrypted

    # Update the token
    account.access_token = "new_token"
    db_session.commit()
    db_session.refresh(account)

    # Encrypted value changed
    assert account.token_encrypted != original_encrypted
    assert account.token_encrypted.startswith("v1:")

    # New plaintext is returned
    assert account.access_token == "new_token"


def test_account_clear_token(db_session: Session) -> None:
    """Test that clearing tokens to None works."""
    account = Account(handle="@clearuser", provider="x")
    account.access_token = "token_to_clear"
    account.refresh_token = "refresh_to_clear"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Clear both tokens
    account.access_token = None
    account.refresh_token = None
    db_session.commit()
    db_session.refresh(account)

    # Both should be None
    assert account.token_encrypted is None
    assert account.refresh_encrypted is None
    assert account.access_token is None
    assert account.refresh_token is None


def test_account_roundtrip_persistence(db_session: Session) -> None:
    """Test that tokens persist correctly across session reloads."""
    # Create and save
    account = Account(handle="@persistuser", provider="x")
    account.access_token = "persistent_token"
    db_session.add(account)
    db_session.commit()
    account_id = account.id

    # Close session
    db_session.close()

    # Reopen session and reload
    engine = db_session.get_bind()
    TestSessionLocal = sessionmaker(bind=engine)
    new_session = TestSessionLocal()

    reloaded_account = new_session.query(Account).filter(Account.id == account_id).first()

    # Token still decrypts correctly
    assert reloaded_account is not None
    assert reloaded_account.access_token == "persistent_token"

    new_session.close()


def test_account_unicode_tokens(db_session: Session) -> None:
    """Test that unicode tokens are handled correctly."""
    account = Account(handle="@unicodeuser", provider="x")
    account.access_token = "token_with_émojis_🔐_and_中文"

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Encrypted
    assert account.token_encrypted is not None
    assert account.token_encrypted.startswith("v1:")

    # Decrypts correctly
    assert account.access_token == "token_with_émojis_🔐_and_中文"


def test_account_long_tokens(db_session: Session) -> None:
    """Test that long tokens (like real JWT) are handled correctly."""
    # Simulate a long JWT-like token
    long_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + ("x" * 500)

    account = Account(handle="@longuser", provider="x")
    account.access_token = long_token

    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    # Still works
    assert account.access_token == long_token
