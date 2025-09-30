"""Web UI routes for Threadify."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Account

router = APIRouter()

# Setup Jinja2 templates
templates = Jinja2Templates(directory="backend/app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Render the main submission form page.

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        HTML response with submission form
    """
    # Get list of connected accounts
    accounts = db.query(Account).all()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "accounts": accounts,
        },
    )
