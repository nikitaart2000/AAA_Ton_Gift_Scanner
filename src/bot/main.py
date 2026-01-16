"""Telegram bot for sending alerts."""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from src.config import settings
from src.core.models import Alert
from src.bot.handlers import start, alerts, osint, market
from src.bot.keyboards import get_main_menu
from src.bot.whitelist import WhitelistMiddleware

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for alerts."""

    def __init__(self):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.running = False

        # Register whitelist middleware
        self.dp.message.middleware(WhitelistMiddleware())
        self.dp.callback_query.middleware(WhitelistMiddleware())

        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register all bot handlers."""
        # Commands
        self.dp.message.register(start.cmd_start, Command("start"))
        self.dp.message.register(start.cmd_help, Command("help"))
        self.dp.message.register(start.cmd_features, Command("features"))
        self.dp.message.register(start.cmd_stats, Command("stats"))
        self.dp.message.register(start.cmd_onchain, Command("onchain"))

        # OSINT commands
        self.dp.message.register(osint.cmd_lookup, Command("lookup", "osint", "whois"))

        # Market data commands (GiftAsset integration)
        self.dp.message.register(market.cmd_deals, Command("deals"))
        self.dp.message.register(market.cmd_market, Command("market"))
        self.dp.message.register(market.cmd_arb, Command("arb", "arbitrage"))

        # Callback handlers for inline buttons
        self.dp.callback_query.register(alerts.handle_mute, F.data.startswith("mute:"))
        self.dp.callback_query.register(alerts.handle_watch, F.data.startswith("watch:"))

    async def start(self):
        """Start the bot."""
        logger.info("Starting Telegram bot...")
        self.running = True

        # Start polling in background
        asyncio.create_task(self._poll())

        logger.info("✅ Telegram bot started")

    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping Telegram bot...")
        self.running = False
        await self.bot.session.close()
        logger.info("✅ Telegram bot stopped")

    async def _poll(self):
        """Poll for updates."""
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Bot polling error: {e}", exc_info=True)

    async def send_alert(self, alert: Alert):
        """Send alert to all active users."""
        # Get whitelist users
        user_ids = settings.whitelist_ids
        if not user_ids:
            logger.warning("No whitelist users configured")
            return

        # Format alert message
        message = self._format_alert(alert)

        # Get inline keyboard (async для получения MRKT listing ID)
        keyboard = await alerts.get_alert_keyboard(alert)

        # Send to each user
        for user_id in user_ids:
            try:
                # Send with photo if available
                if alert.photo_url:
                    await self.bot.send_photo(
                        chat_id=user_id,
                        photo=alert.photo_url,
                        caption=message,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    # Fallback to text-only message
                    await self.bot.send_message(
                        chat_id=user_id, text=message, reply_markup=keyboard, parse_mode="HTML"
                    )
                logger.info(f"Alert sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send alert to user {user_id}: {e}")

    def _format_alert(self, alert: Alert) -> str:
        """Format alert as beautiful HTML message."""
        # Priority indicator
        priority_icon = "🔥" if alert.is_priority else "💎"

        # Black pack indicator
        black_pack_icon = "🖤" if alert.is_black_pack else ""

        # Confidence stars
        confidence_stars = {
            "very_high": "⭐⭐⭐⭐⭐",
            "high": "⭐⭐⭐⭐",
            "medium": "⭐⭐⭐",
            "low": "⭐⭐",
        }
        stars = confidence_stars.get(alert.confidence_level.value, "⭐")

        # Build message
        lines = []

        # Header - с матами!
        if alert.is_priority:
            lines.append(f"{priority_icon} <b>[ЖИРНЫЙ ДИЛ НАХУЙ]</b> {alert.gift_name or 'Неизвестно'}")
        else:
            lines.append(f"{priority_icon} <b>{alert.gift_name or 'Неизвестно'}</b>")

        lines.append("")

        # Basic info
        lines.append(f"💎 <b>Модель:</b> {alert.model or 'Неизвестно'}")
        if alert.backdrop:
            lines.append(f"{black_pack_icon} <b>Фон:</b> {alert.backdrop}")
        if alert.number:
            lines.append(f"🔢 <b>Номер:</b> #{alert.number}")

        lines.append(f"💰 <b>Цена:</b> {alert.price} TON")

        lines.append("")
        lines.append("<b>💸 ПРОФИТ</b>")

        # Profit
        profit_str = f"+{alert.profit_pct}%"
        lines.append(f"├─ <b>Профит:</b> {profit_str} vs {alert.reference_type}")
        lines.append(f"├─ <b>Референс:</b> {alert.reference_price} TON")
        lines.append(f"└─ <b>Уверенность:</b> {stars} {alert.confidence_level.value.upper()}")

        lines.append("")
        lines.append("<b>📊 РЫНОК</b>")

        # Telegram stats (официальная статистика)
        if alert.tg_avg_price:
            lines.append(f"├─ <b>TG Floor:</b> {alert.tg_floor_price} TON")
            lines.append(f"├─ <b>TG Avg:</b> {alert.tg_avg_price} TON")
            if alert.tg_max_price:
                lines.append(f"├─ <b>TG Max:</b> ~{alert.tg_max_price} TON")
            if alert.tg_listed_count:
                lines.append(f"├─ <b>Листингов:</b> {alert.tg_listed_count}")
        else:
            # Fallback на старые флоры
            if alert.floor_black_pack:
                lines.append(f"├─ Black Pack 2-й флор: {alert.floor_black_pack} TON")
            if alert.floor_general:
                floor_label = (
                    "Общий 2-й флор" if alert.floor_black_pack else "2-й флор"
                )
                lines.append(f"├─ {floor_label}: {alert.floor_general} TON")

        lines.append(f"└─ <b>Ликвидность:</b> {alert.liquidity_score}/10")

        # GiftAsset enrichment: Rarity & Arbitrage
        if alert.rarity_score or alert.arbitrage_pct or alert.has_premium_combo:
            lines.append("")
            lines.append("<b>🔮 GIFTASSET</b>")

            if alert.rarity_score:
                tier_emoji = {
                    "Legendary": "🌟",
                    "Epic": "💜",
                    "Rare": "💙",
                    "Uncommon": "💚",
                    "Common": "⚪",
                }.get(alert.rarity_tier, "")
                lines.append(f"├─ <b>Редкость:</b> {alert.rarity_score}/100 {tier_emoji}{alert.rarity_tier or ''}")

            if alert.has_premium_combo:
                lines.append(f"├─ <b>Premium комбо!</b> 💎")

            if alert.arbitrage_pct:
                lines.append(f"├─ <b>Арбитраж:</b> -{alert.arbitrage_pct:.0f}% vs другие маркеты")

            if alert.other_provider_floors:
                for provider, floor in alert.other_provider_floors.items():
                    if provider.lower() != (alert.marketplace.value if alert.marketplace else ""):
                        lines.append(f"│  └─ {provider}: {floor:.1f} TON")

        # Sales data
        if alert.sales_48h > 0:
            lines.append("")
            lines.append(f"🛒 <b>Продаж за 48ч:</b> {alert.sales_48h}")

        lines.append("")

        # Hotness
        fire_icons = "🔥" * min(int(float(alert.hotness)), 5)
        hotness_text = "ГОРЯЧ НАХУЙ" if alert.hotness >= 7 else "Горячесть"
        lines.append(f"{fire_icons} <b>{hotness_text}:</b> {alert.hotness}/10")

        # Timestamp - use event_time if available, otherwise fall back to timestamp
        time_ago = self._time_ago(alert.event_time if alert.event_time else alert.timestamp)
        lines.append(f"⏱️ <i>Листнули {time_ago}</i>")

        # Marketplace info
        if alert.marketplace:
            marketplace_names = {
                "portals": "Portals",
                "mrkt": "MRKT",
                "tonnel": "Tonnel",
                "getgems": "GetGems",
                "fragment": "Fragment",
            }
            mp_name = marketplace_names.get(alert.marketplace.value, alert.marketplace.value.upper())
            lines.append(f"🏪 <i>Маркет: {mp_name}</i>")

        return "\n".join(lines)

    def _time_ago(self, timestamp) -> str:
        """Format timestamp in Calgary timezone (MST/MDT)."""
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        # Ensure timestamp has timezone info
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Convert to Calgary timezone (America/Edmonton = Calgary)
        calgary_tz = ZoneInfo('America/Edmonton')
        calgary_time = timestamp.astimezone(calgary_tz)

        # Format: "Jan 13, 18:45"
        return calgary_time.strftime("%b %d, %H:%M")


# Global bot instance
telegram_bot = TelegramBot()
