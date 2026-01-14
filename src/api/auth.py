"""Telegram Mini App authentication."""

import hmac
import hashlib
import logging
from urllib.parse import parse_qs
from typing import Optional
from fastapi import Header, HTTPException, status

from src.config import settings

logger = logging.getLogger(__name__)


def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Verify Telegram Mini App initData.

    Returns parsed data if valid, None otherwise.
    """
    try:
        # Parse init_data
        parsed = parse_qs(init_data)

        # Extract hash
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Remove hash from data
        parsed.pop("hash", None)

        # Sort and create data_check_string
        data_check_arr = [f"{k}={v[0]}" for k, v in sorted(parsed.items())]
        data_check_string = "\n".join(data_check_arr)

        # Create secret key
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()

        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        # Verify hash
        if calculated_hash != received_hash:
            logger.warning("Invalid Telegram initData hash")
            return None

        # Parse user data
        user_data = parsed.get("user", [None])[0]
        if user_data:
            import json

            user = json.loads(user_data)
            return {"user": user, "auth_date": parsed.get("auth_date", [None])[0]}

        return None

    except Exception as e:
        logger.error(f"Error verifying Telegram initData: {e}")
        return None


async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
) -> dict:
    """
    FastAPI dependency to get current user from Telegram initData.

    For development, allows bypass if no header provided.
    """
    # Development mode: allow access without auth
    if not x_telegram_init_data:
        logger.warning("No Telegram initData provided, using dev user")
        return {
            "user": {"id": settings.whitelist_ids[0] if settings.whitelist_ids else 0},
            "is_dev": True,
        }

    # Verify initData
    user_data = verify_telegram_init_data(x_telegram_init_data, settings.bot_token)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication",
        )

    # Check if user is whitelisted
    user_id = user_data["user"]["id"]
    if user_id not in settings.whitelist_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User not whitelisted"
        )

    return user_data
