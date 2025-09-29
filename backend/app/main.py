"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Threadify",
    description="Turn blog URLs into Twitter/X threads with AI",
    version="0.1.0",
)


@app.get("/healthz")
async def health_check() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse(content={"ok": True}, status_code=200)
