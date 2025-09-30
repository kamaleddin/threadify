"""Tests for Twitter/X OAuth2 PKCE flow."""

import base64
import hashlib

import pytest
from app.security.oauth_x import (
    REQUIRED_SCOPES,
    OAuthError,
    OAuthState,
    OAuthTokens,
    exchange_code_for_tokens,
    generate_code_challenge,
    generate_code_verifier,
    generate_state,
    start_oauth_flow,
)
from httpx import Response


def test_generate_code_verifier() -> None:
    """Test code verifier generation."""
    verifier = generate_code_verifier()

    # Should be a string
    assert isinstance(verifier, str)

    # Should be 43 characters (32 bytes base64url encoded)
    assert len(verifier) == 43

    # Should be base64url safe (no padding, only allowed chars)
    assert all(
        c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in verifier
    )


def test_generate_code_verifier_uniqueness() -> None:
    """Test that code verifiers are unique."""
    verifier1 = generate_code_verifier()
    verifier2 = generate_code_verifier()

    assert verifier1 != verifier2


def test_generate_code_challenge() -> None:
    """Test code challenge generation from verifier."""
    verifier = "test_verifier_string_for_challenge_generation"
    challenge = generate_code_challenge(verifier)

    # Should be a string
    assert isinstance(challenge, str)

    # Should be base64url encoded SHA256 (43 chars)
    assert len(challenge) == 43

    # Verify it's the correct SHA256 hash
    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(expected_digest).decode("ascii").rstrip("=")
    assert challenge == expected_challenge


def test_generate_code_challenge_deterministic() -> None:
    """Test that same verifier produces same challenge."""
    verifier = "same_verifier"
    challenge1 = generate_code_challenge(verifier)
    challenge2 = generate_code_challenge(verifier)

    assert challenge1 == challenge2


def test_generate_state() -> None:
    """Test state parameter generation."""
    state = generate_state()

    # Should be a string
    assert isinstance(state, str)

    # Should be reasonably long (for CSRF protection)
    assert len(state) >= 32


def test_generate_state_uniqueness() -> None:
    """Test that state parameters are unique."""
    state1 = generate_state()
    state2 = generate_state()

    assert state1 != state2


def test_start_oauth_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OAuth flow initiation."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    redirect_uri = "https://example.com/oauth/callback"

    result = start_oauth_flow(redirect_uri)

    # Should return OAuthState
    assert isinstance(result, OAuthState)

    # Should have all required fields
    assert result.code_verifier
    assert result.code_challenge
    assert result.state
    assert result.authorization_url

    # Verify challenge matches verifier
    expected_challenge = generate_code_challenge(result.code_verifier)
    assert result.code_challenge == expected_challenge

    # Verify authorization URL
    assert result.authorization_url.startswith("https://twitter.com/i/oauth2/authorize?")
    assert "client_id=test_client_id" in result.authorization_url
    # redirect_uri is URL-encoded
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Foauth%2Fcallback" in result.authorization_url
    assert f"state={result.state}" in result.authorization_url
    assert f"code_challenge={result.code_challenge}" in result.authorization_url
    assert "code_challenge_method=S256" in result.authorization_url

    # Verify scopes (URL-encoded as '+' or '%20')
    for scope in REQUIRED_SCOPES:
        assert (
            scope.replace(".", "%2E") in result.authorization_url
            or scope in result.authorization_url
        )


def test_start_oauth_flow_missing_client_id() -> None:
    """Test that missing client ID raises error."""
    redirect_uri = "https://example.com/oauth/callback"

    with pytest.raises(OAuthError, match="X_CLIENT_ID not configured"):
        start_oauth_flow(redirect_uri)


def test_exchange_code_for_tokens_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful token exchange."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    # Mock HTTP response
    def mock_http_post(url: str, data: dict, auth: tuple) -> Response:
        from httpx import Request

        assert url == "https://api.twitter.com/2/oauth2/token"
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "test_code"
        assert data["code_verifier"] == "test_verifier"
        assert auth == ("test_client_id", "test_client_secret")

        response = Response(
            200,
            json={
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 7200,
                "scope": "tweet.read tweet.write users.read offline.access",
                "token_type": "bearer",
            },
        )
        response._request = Request("POST", url)
        return response

    result = exchange_code_for_tokens(
        code="test_code",
        code_verifier="test_verifier",
        redirect_uri="https://example.com/callback",
        http_post=mock_http_post,
    )

    assert isinstance(result, OAuthTokens)
    assert result.access_token == "test_access_token"
    assert result.refresh_token == "test_refresh_token"
    assert result.expires_in == 7200
    assert result.scope == "tweet.read tweet.write users.read offline.access"
    assert result.token_type == "bearer"


def test_exchange_code_for_tokens_without_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test token exchange without refresh token."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    def mock_http_post(url: str, data: dict, auth: tuple) -> Response:
        from httpx import Request

        response = Response(
            200,
            json={
                "access_token": "test_access_token",
                "expires_in": 3600,
                "scope": "tweet.read",
                "token_type": "bearer",
            },
        )
        response._request = Request("POST", url)
        return response

    result = exchange_code_for_tokens(
        code="test_code",
        code_verifier="test_verifier",
        redirect_uri="https://example.com/callback",
        http_post=mock_http_post,
    )

    assert result.access_token == "test_access_token"
    assert result.refresh_token is None
    assert result.expires_in == 3600


def test_exchange_code_for_tokens_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test token exchange with HTTP error."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    def mock_http_post(url: str, data: dict, auth: tuple) -> Response:
        from httpx import Request

        response = Response(400, text="Invalid request")
        response._request = Request("POST", url)  # Mock request
        return response

    with pytest.raises(OAuthError, match="Token exchange failed: 400"):
        exchange_code_for_tokens(
            code="invalid_code",
            code_verifier="test_verifier",
            redirect_uri="https://example.com/callback",
            http_post=mock_http_post,
        )


def test_exchange_code_for_tokens_missing_client_id() -> None:
    """Test that missing client ID raises error."""
    with pytest.raises(OAuthError, match="X_CLIENT_ID or X_CLIENT_SECRET not configured"):
        exchange_code_for_tokens(
            code="test_code",
            code_verifier="test_verifier",
            redirect_uri="https://example.com/callback",
        )


def test_exchange_code_for_tokens_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test token exchange with invalid response format."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    def mock_http_post(url: str, data: dict, auth: tuple) -> Response:
        from httpx import Request

        # Missing required 'access_token' field
        response = Response(200, json={"expires_in": 7200})
        response._request = Request("POST", url)
        return response

    with pytest.raises(OAuthError, match="Invalid token response"):
        exchange_code_for_tokens(
            code="test_code",
            code_verifier="test_verifier",
            redirect_uri="https://example.com/callback",
            http_post=mock_http_post,
        )


def test_required_scopes() -> None:
    """Test that required scopes are defined."""
    assert "tweet.read" in REQUIRED_SCOPES
    assert "users.read" in REQUIRED_SCOPES
    assert "tweet.write" in REQUIRED_SCOPES
    assert "offline.access" in REQUIRED_SCOPES


def test_pkce_flow_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test complete PKCE flow from start to token exchange."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    # Step 1: Start OAuth flow
    redirect_uri = "https://example.com/oauth/callback"
    oauth_state = start_oauth_flow(redirect_uri)

    # Store the verifier and state (in real app, stored in session)
    stored_verifier = oauth_state.code_verifier
    stored_state = oauth_state.state

    # User would be redirected to oauth_state.authorization_url
    # After authorization, they return with code and state

    # Step 2: Verify state (in real app)
    returned_state = stored_state  # Should match
    assert returned_state == stored_state

    # Step 3: Exchange code for tokens
    def mock_http_post(url: str, data: dict, auth: tuple) -> Response:
        from httpx import Request

        # Verify the verifier is sent
        assert data["code_verifier"] == stored_verifier
        response = Response(
            200,
            json={
                "access_token": "final_access_token",
                "refresh_token": "final_refresh_token",
                "expires_in": 7200,
                "scope": " ".join(REQUIRED_SCOPES),
                "token_type": "bearer",
            },
        )
        response._request = Request("POST", url)
        return response

    tokens = exchange_code_for_tokens(
        code="authorization_code_from_callback",
        code_verifier=stored_verifier,
        redirect_uri=redirect_uri,
        http_post=mock_http_post,
    )

    # Verify tokens
    assert tokens.access_token == "final_access_token"
    assert tokens.refresh_token == "final_refresh_token"

    # These tokens would then be encrypted and stored in Account model
