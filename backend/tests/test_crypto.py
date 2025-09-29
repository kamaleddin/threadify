"""Tests for AES-GCM encryption/decryption utilities."""

import base64
import os

import pytest
from app.security.crypto import CryptoError, InvalidTokenError, seal, unseal


@pytest.fixture
def test_key() -> bytes:
    """Generate a test encryption key (32 bytes)."""
    return os.urandom(32)


@pytest.fixture
def another_key() -> bytes:
    """Generate a different test encryption key (32 bytes)."""
    return os.urandom(32)


def test_seal_unseal_roundtrip(test_key: bytes) -> None:
    """Test that seal and unseal work correctly together."""
    plaintext = b"Hello, World! This is a secret message."

    # Seal the plaintext
    sealed = seal(plaintext, test_key)

    # Verify format
    assert sealed.startswith("v1:")
    assert len(sealed) > 3  # Has actual data after prefix

    # Unseal and verify
    decrypted = unseal(sealed, test_key)
    assert decrypted == plaintext


def test_seal_produces_different_output_each_time(test_key: bytes) -> None:
    """Test that seal produces different ciphertext each time due to random nonce."""
    plaintext = b"Same message"

    sealed1 = seal(plaintext, test_key)
    sealed2 = seal(plaintext, test_key)

    # Different nonces mean different ciphertext
    assert sealed1 != sealed2

    # But both decrypt to the same plaintext
    assert unseal(sealed1, test_key) == plaintext
    assert unseal(sealed2, test_key) == plaintext


def test_unseal_with_wrong_key_raises_error(test_key: bytes, another_key: bytes) -> None:
    """Test that unsealing with wrong key raises InvalidTokenError."""
    plaintext = b"Secret data"
    sealed = seal(plaintext, test_key)

    # Try to unseal with different key
    with pytest.raises(InvalidTokenError, match="Decryption failed"):
        unseal(sealed, another_key)


def test_unseal_tampered_data_raises_error(test_key: bytes) -> None:
    """Test that unsealing tampered data raises InvalidTokenError."""
    plaintext = b"Original message"
    sealed = seal(plaintext, test_key)

    # Tamper with the data (change one character in the middle)
    # Format: "v1:<base64data>"
    prefix = sealed[:3]  # "v1:"
    encoded = sealed[3:]
    decoded = base64.urlsafe_b64decode(encoded)

    # Flip a bit in the middle of the ciphertext
    tampered_bytes = bytearray(decoded)
    tampered_bytes[15] ^= 0xFF  # XOR to flip bits
    tampered_encoded = base64.urlsafe_b64encode(bytes(tampered_bytes)).decode("ascii")
    tampered_sealed = prefix + tampered_encoded

    # Try to unseal tampered data
    with pytest.raises(InvalidTokenError, match="Decryption failed"):
        unseal(tampered_sealed, test_key)


def test_unseal_invalid_version_prefix_raises_error(test_key: bytes) -> None:
    """Test that unsealing token with wrong version prefix raises InvalidTokenError."""
    plaintext = b"Test data"
    sealed = seal(plaintext, test_key)

    # Change version prefix
    wrong_version = "v2:" + sealed[3:]

    with pytest.raises(InvalidTokenError, match="Invalid token format"):
        unseal(wrong_version, test_key)


def test_unseal_missing_version_prefix_raises_error(test_key: bytes) -> None:
    """Test that unsealing token without version prefix raises InvalidTokenError."""
    plaintext = b"Test data"
    sealed = seal(plaintext, test_key)

    # Remove version prefix
    no_prefix = sealed[3:]

    with pytest.raises(InvalidTokenError, match="Invalid token format"):
        unseal(no_prefix, test_key)


def test_unseal_too_short_data_raises_error(test_key: bytes) -> None:
    """Test that unsealing data shorter than nonce size raises InvalidTokenError."""
    # Create token with data shorter than 12 bytes (nonce size)
    short_data = b"short"
    encoded = base64.urlsafe_b64encode(short_data).decode("ascii")
    short_token = f"v1:{encoded}"

    with pytest.raises(InvalidTokenError, match="Token too short"):
        unseal(short_token, test_key)


def test_seal_with_wrong_key_size_raises_error() -> None:
    """Test that seal with wrong key size raises CryptoError."""
    plaintext = b"Test"
    wrong_size_key = b"tooshort"

    with pytest.raises(CryptoError, match="Key must be exactly 32 bytes"):
        seal(plaintext, wrong_size_key)


def test_unseal_with_wrong_key_size_raises_error(test_key: bytes) -> None:
    """Test that unseal with wrong key size raises CryptoError."""
    plaintext = b"Test"
    sealed = seal(plaintext, test_key)

    wrong_size_key = b"tooshort"
    with pytest.raises(CryptoError, match="Key must be exactly 32 bytes"):
        unseal(sealed, wrong_size_key)


def test_seal_empty_plaintext(test_key: bytes) -> None:
    """Test that seal works with empty plaintext."""
    plaintext = b""
    sealed = seal(plaintext, test_key)

    decrypted = unseal(sealed, test_key)
    assert decrypted == plaintext


def test_seal_large_plaintext(test_key: bytes) -> None:
    """Test that seal works with large plaintext."""
    # 1MB of data
    plaintext = os.urandom(1024 * 1024)
    sealed = seal(plaintext, test_key)

    decrypted = unseal(sealed, test_key)
    assert decrypted == plaintext


def test_seal_unicode_text(test_key: bytes) -> None:
    """Test that seal works with unicode text."""
    plaintext = "Hello 世界! 🔐".encode()
    sealed = seal(plaintext, test_key)

    decrypted = unseal(sealed, test_key)
    assert decrypted == plaintext
    assert decrypted.decode("utf-8") == "Hello 世界! 🔐"
