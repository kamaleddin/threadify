"""AES-GCM encryption utilities for sealing secrets at rest."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from passlib.context import CryptContext


class CryptoError(Exception):
    """Base exception for crypto operations."""

    pass


class InvalidTokenError(CryptoError):
    """Raised when a token cannot be decrypted or is invalid."""

    pass


def seal(plaintext: bytes, key: bytes) -> str:
    """
    Encrypt plaintext using AES-GCM with a random nonce.

    Args:
        plaintext: Data to encrypt
        key: 32-byte encryption key

    Returns:
        Base64url-encoded string with format "v1:<nonce><ciphertext>"

    Raises:
        CryptoError: If encryption fails
    """
    if len(key) != 32:
        raise CryptoError("Key must be exactly 32 bytes")

    try:
        # Generate random 12-byte nonce
        nonce = os.urandom(12)

        # Create AESGCM cipher
        aesgcm = AESGCM(key)

        # Encrypt plaintext (includes authentication tag)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # Combine nonce + ciphertext and encode
        sealed = nonce + ciphertext
        encoded = base64.urlsafe_b64encode(sealed).decode("ascii")

        # Add version prefix
        return f"v1:{encoded}"

    except Exception as e:
        raise CryptoError(f"Encryption failed: {e}") from e


def unseal(token: str, key: bytes) -> bytes:
    """
    Decrypt a sealed token using AES-GCM.

    Args:
        token: Sealed token from seal() with format "v1:<encoded_data>"
        key: 32-byte encryption key (must match the key used to seal)

    Returns:
        Decrypted plaintext bytes

    Raises:
        InvalidTokenError: If token is malformed, tampered with, or uses wrong key
        CryptoError: If decryption fails
    """
    if len(key) != 32:
        raise CryptoError("Key must be exactly 32 bytes")

    try:
        # Check version prefix
        if not token.startswith("v1:"):
            raise InvalidTokenError("Invalid token format: missing or unknown version prefix")

        # Remove version prefix and decode
        encoded_data = token[3:]  # Skip "v1:"
        try:
            sealed = base64.urlsafe_b64decode(encoded_data)
        except Exception as e:
            raise InvalidTokenError(f"Invalid base64 encoding: {e}") from e

        # Extract nonce (first 12 bytes) and ciphertext (remaining bytes)
        if len(sealed) < 12:
            raise InvalidTokenError("Token too short: must contain at least nonce")

        nonce = sealed[:12]
        ciphertext = sealed[12:]

        # Create AESGCM cipher and decrypt
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext
        except Exception as e:
            # This catches authentication failures (wrong key or tampered data)
            raise InvalidTokenError("Decryption failed: invalid key or tampered data") from e

    except InvalidTokenError:
        # Re-raise InvalidTokenError as-is
        raise
    except Exception as e:
        # Wrap any other exceptions
        raise CryptoError(f"Unseal failed: {e}") from e


# Password hashing for API tokens
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain password using bcrypt."""
    return pwd_context.hash(plain_password)  # type: ignore[no-any-return]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)  # type: ignore[no-any-return]
