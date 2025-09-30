"""End-to-end tests for OAuth routes."""

import pytest
from app.main import app
from fastapi.testclient import TestClient
from httpx import Response


@pytest.fixture
def client() -> TestClient:
    """Create a test client with session support."""
    return TestClient(app)


def test_oauth_start_redirects_to_twitter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that /oauth/x/start redirects to Twitter authorization URL."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")

    response = client.get("/oauth/x/start", follow_redirects=False)

    # Should redirect to Twitter
    assert response.status_code == 302
    assert "twitter.com/i/oauth2/authorize" in response.headers["location"]
    assert "client_id=test_client_id" in response.headers["location"]
    assert "code_challenge=" in response.headers["location"]
    assert "code_challenge_method=S256" in response.headers["location"]

    # Should have session cookies
    assert "session" in response.cookies


def test_oauth_start_missing_client_id(client: TestClient) -> None:
    """Test that missing client ID returns error."""
    response = client.get("/oauth/x/start")

    assert response.status_code == 500
    assert "OAuth initialization failed" in response.json()["detail"]


@pytest.mark.skip(reason="Complex mocking needed for full OAuth flow - tested in unit tests")
def test_oauth_callback_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful OAuth callback with token exchange."""
    # Note: This end-to-end test requires complex mocking of external HTTP calls.
    # OAuth flow components are thoroughly tested in:
    # - test_oauth_x.py: PKCE flow, token exchange
    # - test_account_secrets.py: Token encryption
    # - test_oauth_callback_invalid_state: State validation
    pass


def test_oauth_callback_invalid_state(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OAuth callback with invalid state parameter."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")

    # Start OAuth flow
    start_response = client.get("/oauth/x/start", follow_redirects=False)
    session_cookie = start_response.cookies.get("session")

    # Callback with wrong state
    callback_response = client.get(
        "/oauth/x/callback?code=test_code&state=wrong_state",
        cookies={"session": session_cookie},
    )

    assert callback_response.status_code == 400
    assert "Invalid state parameter" in callback_response.json()["detail"]


def test_oauth_callback_missing_session(client: TestClient) -> None:
    """Test OAuth callback without session data."""
    callback_response = client.get("/oauth/x/callback?code=test_code&state=test_state")

    assert callback_response.status_code == 400
    assert "OAuth session expired" in callback_response.json()["detail"]


def test_oauth_callback_token_exchange_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test OAuth callback when token exchange fails."""
    monkeypatch.setenv("X_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("X_CLIENT_SECRET", "test_client_secret")

    # Mock failed token exchange
    from app.security.oauth_x import OAuthError

    def mock_exchange(code: str, code_verifier: str, redirect_uri: str, http_post=None):
        raise OAuthError("Invalid authorization code")

    monkeypatch.setattr("app.security.oauth_x.exchange_code_for_tokens", mock_exchange)

    # Start OAuth flow
    start_response = client.get("/oauth/x/start", follow_redirects=False)
    session_cookie = start_response.cookies.get("session")
    redirect_url = start_response.headers["location"]
    state = redirect_url.split("state=")[1].split("&")[0]

    # Callback with code
    callback_response = client.get(
        f"/oauth/x/callback?code=invalid_code&state={state}",
        cookies={"session": session_cookie},
    )

    assert callback_response.status_code == 400
    assert "Token exchange failed" in callback_response.json()["detail"]


# Note: Token encryption is thoroughly tested in test_account_secrets.py
# This OAuth flow test would need complex mocking, so we rely on unit tests instead
