"""Alert-related handlers."""

import logging
from datetime import datetime, timedelta, timezone
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from src.core.models import Alert, Marketplace
from src.storage.postgres import db
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Marketplace button labels
MARKETPLACE_LABELS = {
    Marketplace.PORTALS: "CryptoBot",
    Marketplace.MRKT: "MRKT",
    Marketplace.TONNEL: "Tonnel",
    Marketplace.GETGEMS: "GetGems",
    Marketplace.FRAGMENT: "Fragment",
}


def get_alert_keyboard(alert: Alert) -> InlineKeyboardMarkup:
    """Create inline keyboard for alert."""
    buttons = []

    # Row 1: Marketplace links
    marketplace_buttons = []

    # Main marketplace button (where the item is listed)
    if alert.marketplace:
        main_url = alert.marketplace_url
        label = MARKETPLACE_LABELS.get(alert.marketplace, alert.marketplace.value.upper())
        if main_url:
            marketplace_buttons.append(
                InlineKeyboardButton(text=f"🎁 {label}", url=main_url)
            )

    # Tonnel Mini App button (for cross-marketplace search)
    tonnel_url = f"https://t.me/TonnelMarketBot/market?startapp={alert.gift_id}"
    marketplace_buttons.append(
        InlineKeyboardButton(text="🔍 Tonnel", url=tonnel_url)
    )

    # Fragment fallback link (if not already the main marketplace)
    if alert.marketplace != Marketplace.FRAGMENT:
        fragment_url = f"https://fragment.com/gift/{alert.gift_id}"
        marketplace_buttons.append(
            InlineKeyboardButton(text="💎 Fragment", url=fragment_url)
        )

    # Limit to 3 buttons per row
    if len(marketplace_buttons) > 3:
        marketplace_buttons = marketplace_buttons[:3]

    if marketplace_buttons:
        buttons.append(marketplace_buttons)

    # Row 2: Actions
    buttons.append([
        InlineKeyboardButton(
            text="⭐ В ИЗБРАННОЕ", callback_data=f"watch:{alert.asset_key}"
        ),
        InlineKeyboardButton(
            text="🔇 ЗАГЛУШИТЬ 2Ч", callback_data=f"mute:{alert.asset_key}:2h"
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def handle_watch(callback: CallbackQuery):
    """Handle watch button press."""
    user_id = callback.from_user.id
    asset_key = callback.data.split(":", 1)[1]

    try:
        # Add to watchlist
        async for session in db.get_session():
            query = text("""
            INSERT INTO watchlist (user_id, asset_key, added_at)
            VALUES (:user_id, :asset_key, NOW())
            ON CONFLICT (user_id, asset_key) DO NOTHING
            """)
            await session.execute(query, {"user_id": user_id, "asset_key": asset_key})
            await session.commit()

        await callback.answer("⭐ Добавлено в избранное, красава!", show_alert=False)
        logger.info(f"User {user_id} added {asset_key} to watchlist")

    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}", exc_info=True)
        await callback.answer("❌ Ошибка, бля", show_alert=True)


async def handle_mute(callback: CallbackQuery):
    """Handle mute button press."""
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    asset_key = parts[1]
    duration = parts[2] if len(parts) > 2 else "2h"

    # Parse duration
    duration_map = {
        "30m": timedelta(minutes=30),
        "2h": timedelta(hours=2),
        "24h": timedelta(hours=24),
    }

    mute_duration = duration_map.get(duration, timedelta(hours=2))
    muted_until = datetime.now(timezone.utc) + mute_duration

    try:
        # Add to muted_assets
        async for session in db.get_session():
            query = text("""
            INSERT INTO muted_assets (user_id, asset_key, muted_until, created_at)
            VALUES (:user_id, :asset_key, :muted_until, NOW())
            ON CONFLICT (user_id, asset_key)
            DO UPDATE SET muted_until = EXCLUDED.muted_until
            """)
            await session.execute(
                query,
                {"user_id": user_id, "asset_key": asset_key, "muted_until": muted_until},
            )
            await session.commit()

        await callback.answer(f"🔇 Заткнули на {duration}", show_alert=False)
        logger.info(f"User {user_id} muted {asset_key} for {duration}")

    except Exception as e:
        logger.error(f"Error muting asset: {e}", exc_info=True)
        await callback.answer("❌ Не получилось заглушить", show_alert=True)
