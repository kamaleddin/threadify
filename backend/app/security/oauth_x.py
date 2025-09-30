"""OAuth2 PKCE flow for Twitter/X authentication."""

import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import get_settings


class OAuthError(Exception):
    """Raised when OAuth flow encounters an error."""

    pass


@dataclass
class OAuthState:
    """OAuth state for PKCE flow."""

    code_verifier: str
    code_challenge: str
    state: str
    authorization_url: str


@dataclass
class OAuthTokens:
    """OAuth tokens from token exchange."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str
    token_type: str = "bearer"


# Required scopes for Twitter/X API
REQUIRED_SCOPES = [
    "tweet.read",
    "users.read",
    "tweet.write",
    "offline.access",
]


def generate_code_verifier() -> str:
    """
    Generate a cryptographically random code verifier for PKCE.

    Returns:
        Base64url-encoded random string (43-128 characters)
    """
    # Generate 32 random bytes (will be 43 chars when base64url encoded)
    random_bytes = secrets.token_bytes(32)
    # Base64url encode (no padding)
    code_verifier = base64.urlsafe_b64encode(random_bytes).decode("ascii").rstrip("=")
    return code_verifier


def generate_code_challenge(code_verifier: str) -> str:
    """
    Generate code challenge from verifier using S256 method.

    Args:
        code_verifier: The code verifier string

    Returns:
        Base64url-encoded SHA256 hash of the verifier
    """
    # SHA256 hash the verifier
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    # Base64url encode (no padding)
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_challenge


def generate_state() -> str:
    """
    Generate a random state parameter for CSRF protection.

    Returns:
        Random string
    """
    return secrets.token_urlsafe(32)


def start_oauth_flow(redirect_uri: str) -> OAuthState:
    """
    Start the OAuth2 PKCE flow by generating parameters and authorization URL.

    Args:
        redirect_uri: The callback URL for OAuth

    Returns:
        OAuthState with verifier, challenge, state, and authorization URL

    Raises:
        OAuthError: If configuration is invalid
    """
    settings = get_settings()

    if not settings.x_client_id:
        raise OAuthError("X_CLIENT_ID not configured")

    # Generate PKCE parameters
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = generate_state()

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": settings.x_client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(REQUIRED_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    authorization_url = f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"

    return OAuthState(
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        state=state,
        authorization_url=authorization_url,
    )


def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    http_post: Callable[[str, dict, tuple], httpx.Response] | None = None,
) -> OAuthTokens:
    """
    Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code from callback
        code_verifier: The original code verifier
        redirect_uri: The callback URL (must match authorization)
        http_post: Optional HTTP POST function (for testing)

    Returns:
        OAuthTokens with access token, refresh token, etc.

    Raises:
        OAuthError: If token exchange fails
    """
    settings = get_settings()

    if not settings.x_client_id or not settings.x_client_secret:
        raise OAuthError("X_CLIENT_ID or X_CLIENT_SECRET not configured")

    # Default HTTP client
    if http_post is None:
        http_post = _default_http_post

    # Token endpoint
    token_url = "https://api.twitter.com/2/oauth2/token"

    # Request parameters
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "client_id": settings.x_client_id,
    }

    # Basic auth with client credentials
    auth = (settings.x_client_id, settings.x_client_secret)

    try:
        response = http_post(token_url, data=data, auth=auth)  # type: ignore[call-arg]
        response.raise_for_status()
        token_data = response.json()

        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_in=token_data.get("expires_in", 7200),
            scope=token_data.get("scope", ""),
            token_type=token_data.get("token_type", "bearer"),
        )
    except httpx.HTTPStatusError as e:
        error_detail = e.response.text if e.response else "Unknown error"
        raise OAuthError(f"Token exchange failed: {e.response.status_code} - {error_detail}") from e
    except KeyError as e:
        raise OAuthError(f"Invalid token response: missing {e}") from e
    except Exception as e:
        raise OAuthError(f"Token exchange failed: {e}") from e


def _default_http_post(url: str, data: dict, auth: tuple) -> httpx.Response:
    """Default HTTP POST client using httpx."""
    with httpx.Client(timeout=30.0) as client:
        response: httpx.Response = client.post(
            url,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return response
