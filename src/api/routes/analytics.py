"""API routes for analytics - simplified."""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/{asset_key:path}")
async def get_asset_analytics(asset_key: str):
    """Get asset analytics - mock for now."""
    return {"asset_key": asset_key, "status": "coming soon"}
