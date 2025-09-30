"""OAuth2 routes for Twitter/X authentication."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.dao import create_account, get_account_by_handle
from app.db.schema import AccountCreate
from app.security.oauth_x import (
    OAuthError,
    exchange_code_for_tokens,
    start_oauth_flow,
)

router = APIRouter(prefix="/oauth/x", tags=["oauth"])


@router.get("/start")
async def oauth_start(request: Request) -> RedirectResponse:
    """
    Start the OAuth2 PKCE flow for Twitter/X.

    Generates PKCE parameters and redirects user to Twitter authorization page.
    Stores verifier and state in session for callback validation.
    """
    # Build redirect URI (callback URL)
    redirect_uri = str(request.url_for("oauth_callback"))

    try:
        # Start OAuth flow
        oauth_state = start_oauth_flow(redirect_uri)

        # Store verifier and state in session (for callback)
        # In production, use secure session storage (Redis, encrypted cookies, etc.)
        request.session["oauth_verifier"] = oauth_state.code_verifier
        request.session["oauth_state"] = oauth_state.state

        # Redirect to Twitter authorization
        return RedirectResponse(url=oauth_state.authorization_url, status_code=302)

    except OAuthError as e:
        raise HTTPException(status_code=500, detail=f"OAuth initialization failed: {e}") from e


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(..., description="Authorization code from Twitter"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    db: Session = Depends(get_db),
) -> dict:
    """
    OAuth2 callback endpoint.

    Receives authorization code from Twitter, validates state,
    exchanges code for tokens, and stores encrypted tokens in database.
    """
    # Retrieve stored verifier and state from session
    stored_verifier = request.session.get("oauth_verifier")
    stored_state = request.session.get("oauth_state")

    if not stored_verifier or not stored_state:
        raise HTTPException(status_code=400, detail="OAuth session expired or invalid")

    # Verify state parameter (CSRF protection)
    if state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Build redirect URI (must match the one used in start)
    redirect_uri = str(request.url_for("oauth_callback"))

    try:
        # Exchange code for tokens
        tokens = exchange_code_for_tokens(
            code=code,
            code_verifier=stored_verifier,
            redirect_uri=redirect_uri,
        )

        # TODO: Get user info from Twitter API to get handle
        # For now, use a placeholder handle
        # In production, make a request to https://api.twitter.com/2/users/me
        handle = f"@user_{code[:8]}"  # Placeholder

        # Check if account already exists
        account = get_account_by_handle(db, handle)

        if account:
            # Update existing account tokens (using setattr to avoid mypy method-assign error)
            setattr(account, "access_token", tokens.access_token)
            setattr(account, "refresh_token", tokens.refresh_token)
            account.scopes = tokens.scope
            db.commit()
        else:
            # Create new account with encrypted tokens
            account_data = AccountCreate(
                handle=handle,
                provider="x",
                scopes=tokens.scope,
            )
            account = create_account(db, account_data)

            # Set tokens (will be encrypted automatically via hybrid properties)
            setattr(account, "access_token", tokens.access_token)
            setattr(account, "refresh_token", tokens.refresh_token)
            db.commit()

        # Clear session
        request.session.pop("oauth_verifier", None)
        request.session.pop("oauth_state", None)

        return {
            "success": True,
            "account_id": account.id,
            "handle": account.handle,
            "message": "OAuth authentication successful",
        }

    except OAuthError as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {e}") from e
