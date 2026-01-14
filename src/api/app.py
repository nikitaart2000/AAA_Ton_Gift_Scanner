"""FastAPI application for Mini App."""

import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import deals, analytics, watchlist, websocket
from src.api.auth import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="TON Gifts Terminal API",
    description="REST API for TON Gifts Mini App trading terminal",
    version="1.0.0",
)

# CORS middleware for Telegram WebView
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.telegram.org", "*"],  # Allow Telegram WebView
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ton-gifts-terminal-api"}


# Include routers
app.include_router(deals.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(websocket.router, prefix="/api")


# Protected route example
@app.get("/api/me")
async def get_me(user_data: dict = Depends(get_current_user)):
    """Get current user info."""
    return user_data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
