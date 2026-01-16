"""Alert-related handlers."""

import logging
from datetime import datetime, timedelta, timezone
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from src.core.models import Alert, Marketplace
from src.storage.postgres import db
from src.services.mrkt_api import mrkt_api
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Marketplace button labels
MARKETPLACE_LABELS = {
    Marketplace.PORTALS: "Portals",
    Marketplace.MRKT: "MRKT",
    Marketplace.TONNEL: "Tonnel",
    Marketplace.GETGEMS: "GetGems",
    Marketplace.FRAGMENT: "Fragment",
}


async def get_alert_keyboard(alert: Alert) -> InlineKeyboardMarkup:
    """Create inline keyboard for alert."""
    buttons = []

    # Row 1: Main marketplace button (where the item is listed) - DIRECT LISTING LINK
    if alert.marketplace:
        label = MARKETPLACE_LABELS.get(alert.marketplace, alert.marketplace.value.upper())
        listing_id = None

        # Для MRKT получаем listing_id через API
        if alert.marketplace == Marketplace.MRKT:
            try:
                listing_id = await mrkt_api.get_listing_id(alert.gift_id)
                if listing_id:
                    logger.debug(f"Got MRKT listing ID for {alert.gift_id}: {listing_id}")
            except Exception as e:
                logger.warning(f"Failed to get MRKT listing ID: {e}")

        # Get actual marketplace URL (not TG stats!)
        main_url = alert.marketplace.get_gift_url(alert.gift_id, listing_id)

        if main_url:
            buttons.append([
                InlineKeyboardButton(text=f"🎁 Открыть в {label}", url=main_url)
            ])

    # Row 2: TG Stats + Actions
    tg_stats_url = Marketplace.get_telegram_stats_url(alert.gift_id)
    buttons.append([
        InlineKeyboardButton(text="📊 TG Статистика", url=tg_stats_url),
        InlineKeyboardButton(
            text="⭐ В избранное", callback_data=f"watch:{alert.asset_key}"
        ),
    ])

    # Row 3: Mute + Fragment
    fragment_url = f"https://fragment.com/gift/{alert.gift_id}"
    buttons.append([
        InlineKeyboardButton(
            text="🔇 Заглушить 2ч", callback_data=f"mute:{alert.asset_key}:2h"
        ),
        InlineKeyboardButton(text="💎 Fragment", url=fragment_url),
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
