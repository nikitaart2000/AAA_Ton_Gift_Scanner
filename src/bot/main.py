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

        # Historical price validation (7d data)
        if alert.historical_discount_pct and alert.validation_confidence:
            if alert.validation_confidence in ("high", "medium"):
                lines.append("")
                lines.append("<b>📈 ИСТОР. ВАЛИДАЦИЯ</b>")
                conf_icon = "✅" if alert.validation_confidence == "high" else "🔸"
                lines.append(f"├─ {conf_icon} <b>vs 7д AVG:</b> -{alert.historical_discount_pct}%")
                if alert.historical_avg_price:
                    lines.append(f"└─ <b>7д AVG:</b> {alert.historical_avg_price:.1f} TON")

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

        # AI Verdict - анализ простым языком с матами
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        verdict = self._generate_verdict(alert)
        lines.append(verdict)

        return "\n".join(lines)

    def _generate_verdict(self, alert: Alert) -> str:
        """Generate AI verdict with profanity - простой анализ сделки."""
        reasons_good = []
        reasons_bad = []
        score = 0  # -10 to +10

        # 1. Профит vs референс
        if alert.profit_pct:
            profit = float(alert.profit_pct)
            if profit >= 30:
                reasons_good.append(f"профит {profit}% - это пиздец как много")
                score += 3
            elif profit >= 20:
                reasons_good.append(f"профит {profit}% - норм тема")
                score += 2
            elif profit >= 10:
                reasons_good.append(f"профит {profit}% - есть куда расти")
                score += 1
            else:
                reasons_bad.append(f"профит {profit}% - хуйня какая-то")
                score -= 1

        # 2. Уверенность
        if alert.confidence_level:
            conf = alert.confidence_level.value
            if conf == "very_high":
                reasons_good.append("данные железобетонные")
                score += 2
            elif conf == "high":
                reasons_good.append("данные надежные")
                score += 1
            elif conf == "low":
                reasons_bad.append("данных маловато, хз че там")
                score -= 1

        # 3. Историческая валидация (7д)
        if alert.historical_discount_pct and alert.validation_confidence:
            disc = float(alert.historical_discount_pct)
            if alert.validation_confidence in ("high", "medium"):
                if disc >= 20:
                    reasons_good.append(f"на {disc}% ниже средней за неделю - ахуенно")
                    score += 2
                elif disc >= 10:
                    reasons_good.append(f"на {disc}% ниже недельной средней")
                    score += 1

        # 4. Арбитраж между маркетами
        if alert.arbitrage_pct:
            arb = float(alert.arbitrage_pct)
            if arb >= 15:
                reasons_good.append(f"арбитраж {arb}% - можно перепродать дороже")
                score += 2
            elif arb >= 8:
                reasons_good.append(f"есть арбитраж {arb}%")
                score += 1

        # 5. Редкость (GiftAsset)
        if alert.rarity_score:
            rarity = float(alert.rarity_score)
            if rarity >= 80:
                reasons_good.append(f"редкость {rarity}/100 - легенда нахуй")
                score += 2
            elif rarity >= 60:
                reasons_good.append(f"редкость {rarity}/100 - норм")
                score += 1
            elif rarity <= 30:
                reasons_bad.append(f"редкость {rarity}/100 - обычная хуйня")
                score -= 1

        # 6. Premium комбо
        if alert.has_premium_combo:
            reasons_good.append("premium комбо - ценится выше")
            score += 1

        # 7. Ликвидность
        if alert.liquidity_score:
            liq = float(alert.liquidity_score)
            if liq >= 8:
                reasons_good.append(f"ликвидность {liq}/10 - продашь быстро")
                score += 1
            elif liq <= 3:
                reasons_bad.append(f"ликвидность {liq}/10 - хуй продашь")
                score -= 2

        # 8. Продажи за 48ч
        if alert.sales_48h:
            if alert.sales_48h >= 10:
                reasons_good.append(f"{alert.sales_48h} продаж за 48ч - активно торгуется")
                score += 1
            elif alert.sales_48h <= 2:
                reasons_bad.append(f"только {alert.sales_48h} продаж за 48ч - мертвяк")
                score -= 1

        # 9. Black Pack бонус
        if alert.is_black_pack:
            reasons_good.append("Black Pack - всегда в цене")
            score += 1

        # 10. Горячесть
        if alert.hotness:
            hot = float(alert.hotness)
            if hot >= 8:
                reasons_good.append("горячая тема прям сейчас")
                score += 1

        # Собираем вердикт
        lines = ["<b>🤖 ВЕРДИКТ</b>"]

        if reasons_good:
            lines.append("")
            lines.append("✅ <b>Плюсы:</b>")
            for r in reasons_good[:4]:  # Макс 4 причины
                lines.append(f"  • {r}")

        if reasons_bad:
            lines.append("")
            lines.append("❌ <b>Минусы:</b>")
            for r in reasons_bad[:3]:  # Макс 3 причины
                lines.append(f"  • {r}")

        # Итоговая рекомендация
        lines.append("")
        if score >= 5:
            lines.append("💰 <b>ПОКУПАЙ НАХУЙ!</b> Отличная сделка, не тупи.")
        elif score >= 3:
            lines.append("👍 <b>Бери, норм тема.</b> Профит будет.")
        elif score >= 1:
            lines.append("🤔 <b>Можно брать</b>, но без фанатизма.")
        elif score >= -1:
            lines.append("😐 <b>Подумай, братик.</b> Не самый топ вариант.")
        else:
            lines.append("👎 <b>Хуйня, не бери.</b> Найдешь лучше.")

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
