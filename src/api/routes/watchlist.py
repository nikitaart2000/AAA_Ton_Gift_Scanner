"""API routes for watchlist - simplified."""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
async def get_watchlist(user_id: int):
    """Get watchlist - mock for now."""
    return {"items": [], "total": 0}
