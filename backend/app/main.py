"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import router as api_router
from app.config import get_settings
from app.web.oauth_routes import router as oauth_router
from app.web.routes import router as web_router

app = FastAPI(
    title="Threadify",
    description="Turn blog URLs into Twitter/X threads with AI",
    version="0.1.0",
)

# Add session middleware for OAuth flow
# In production, use a secret key from settings
settings = get_settings()
session_secret = settings.secret_aes_key or "development-secret-key-change-in-production"
app.add_middleware(SessionMiddleware, secret_key=session_secret)

# Mount static files
app.mount("/static", StaticFiles(directory="backend/app/web/static"), name="static")

# Include routers
app.include_router(oauth_router)
app.include_router(web_router)
app.include_router(api_router)


@app.get("/healthz")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"ok": True}, status_code=200)
