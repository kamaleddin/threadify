"""API authentication middleware."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import ApiToken
from app.security.crypto import verify_password

security = HTTPBearer()


def verify_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> ApiToken:
    """Verify API token and return the associated ApiToken object."""
    token = credentials.credentials

    # Look up all API tokens and check against hashed versions
    api_tokens = db.query(ApiToken).filter(ApiToken.is_active == True).all()

    for api_token in api_tokens:
        if verify_password(token, api_token.token_hash):
            return api_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_api_token(
    api_token: ApiToken = Depends(verify_api_token),
) -> ApiToken:
    """Get the current authenticated API token."""
    return api_token