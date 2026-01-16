"""Market data handlers - /deals, /market commands."""

import logging
from aiogram.types import Message

from src.services.giftasset_cache import giftasset_cache
from src.services.giftasset_api import get_giftasset_api

logger = logging.getLogger(__name__)


async def cmd_deals(message: Message):
    """Handle /deals command - show best deals from GiftAsset."""
    await message.answer("🔍 <b>Ищу лучшие сделки...</b>", parse_mode="HTML")

    try:
        # Get cached deals first (fast)
        deals = giftasset_cache.get_best_deals(limit=10)

        if not deals:
            # Try to fetch fresh if cache is empty
            api = get_giftasset_api()
            if api:
                await message.answer(
                    "⚠️ Кэш пуст, обновляю данные... Подожди пару секунд.",
                    parse_mode="HTML"
                )
                await giftasset_cache._update_cache()
                deals = giftasset_cache.get_best_deals(limit=10)

        if not deals:
            await message.answer(
                "❌ Не удалось получить данные о сделках.\n"
                "Проверь, что GIFTASSET_API_KEY настроен в .env",
                parse_mode="HTML"
            )
            return

        # Format deals
        lines = []
        lines.append("🔥 <b>ТОП СДЕЛКИ ОТ GIFTASSET</b>")
        lines.append("")

        for i, deal in enumerate(deals, 1):
            # Rarity emoji
            tier_emoji = {
                "Legendary": "🌟",
                "Epic": "💜",
                "Rare": "💙",
                "Uncommon": "💚",
                "Common": "⚪",
            }.get(deal.rarity.tier, "")

            # Premium flag
            premium = " 💎" if deal.rarity.has_premium_attribute else ""

            # Format line
            lines.append(f"<b>{i}. {deal.gift_name}</b>{premium}")
            lines.append(f"   💰 <b>{deal.price:.1f} TON</b> на {deal.provider.upper()}")

            if deal.discount_pct:
                lines.append(f"   📉 <b>-{deal.discount_pct:.0f}%</b> от avg floor")

            if deal.market_floor.avg_floor:
                lines.append(f"   📊 Avg floor: {deal.market_floor.avg_floor:.1f} TON")

            # Rarity
            if deal.rarity.final_score > 0:
                lines.append(f"   {tier_emoji} Rarity: {deal.rarity.final_score:.0f}/100 ({deal.rarity.tier})")

            # Provider floors comparison
            if deal.market_floor.providers:
                provider_info = []
                for prov, pf in deal.market_floor.providers.items():
                    if pf.model_floor:
                        provider_info.append(f"{prov}: {pf.model_floor:.0f}")
                if provider_info:
                    lines.append(f"   🏪 {' | '.join(provider_info[:3])}")

            lines.append("")

        # Cache stats
        stats = giftasset_cache.get_cache_stats()
        if stats["last_update"]:
            lines.append(f"<i>📅 Обновлено: {stats['last_update'][:19]}</i>")

        await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in /deals: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка: {str(e)[:100]}",
            parse_mode="HTML"
        )


async def cmd_market(message: Message):
    """Handle /market command - show market analytics."""
    await message.answer("📊 <b>Загружаю маркет-аналитику...</b>", parse_mode="HTML")

    try:
        api = get_giftasset_api()
        if not api:
            await message.answer(
                "❌ GiftAsset API не настроен.\n"
                "Добавь GIFTASSET_API_KEY в .env",
                parse_mode="HTML"
            )
            return

        # Fetch market data in parallel
        import asyncio
        marketcap_task = api.get_collection_marketcap()
        health_task = api.get_collection_health()
        volumes_task = api.get_provider_volumes()

        marketcap, health, volumes = await asyncio.gather(
            marketcap_task, health_task, volumes_task,
            return_exceptions=True
        )

        lines = []
        lines.append("📊 <b>МАРКЕТ АНАЛИТИКА</b>")
        lines.append("")

        # Provider volumes
        if isinstance(volumes, dict) and volumes:
            lines.append("<b>🏪 ОБЪЁМЫ ПО МАРКЕТПЛЕЙСАМ</b>")
            for provider, data in list(volumes.items())[:5]:
                if isinstance(data, dict):
                    vol_24h = data.get("volume_24h", 0)
                    vol_total = data.get("volume_total", 0)
                    lines.append(f"├─ <b>{provider}</b>: {vol_24h:.0f} TON (24ч) | {vol_total:.0f} TON (всего)")
            lines.append("")

        # Market cap by collection
        if isinstance(marketcap, dict) and marketcap:
            lines.append("<b>💎 ТОП КОЛЛЕКЦИИ ПО КАПЕ</b>")
            # Sort by market cap if possible
            if isinstance(marketcap, list):
                sorted_mc = sorted(marketcap, key=lambda x: x.get("market_cap", 0), reverse=True)[:5]
            else:
                sorted_mc = list(marketcap.items())[:5] if isinstance(marketcap, dict) else []

            for item in sorted_mc:
                if isinstance(item, dict):
                    name = item.get("collection_name", "Unknown")
                    cap = item.get("market_cap", 0)
                    floor = item.get("floor_price", 0)
                    lines.append(f"├─ <b>{name}</b>: {cap:.0f} TON (floor: {floor:.1f})")
                elif isinstance(item, tuple):
                    name, data = item
                    if isinstance(data, dict):
                        cap = data.get("market_cap", 0)
                        lines.append(f"├─ <b>{name}</b>: {cap:.0f} TON")
            lines.append("")

        # Health index
        if isinstance(health, dict) and health:
            lines.append("<b>💚 ЗДОРОВЬЕ КОЛЛЕКЦИЙ</b>")
            health_items = list(health.items())[:5] if isinstance(health, dict) else health[:5]
            for item in health_items:
                if isinstance(item, tuple):
                    name, data = item
                    if isinstance(data, dict):
                        index = data.get("health_index", 0)
                        liquidity = data.get("liquidity", 0)
                        lines.append(f"├─ <b>{name}</b>: {index:.0f}/100 (лик: {liquidity:.0f})")
                elif isinstance(item, dict):
                    name = item.get("collection_name", "Unknown")
                    index = item.get("health_index", 0)
                    lines.append(f"├─ <b>{name}</b>: {index:.0f}/100")
            lines.append("")

        # Cache stats
        stats = giftasset_cache.get_cache_stats()
        lines.append(f"<i>📦 В кэше: {stats['models_cached']} моделей, {stats['deals_cached']} сделок</i>")

        await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in /market: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка: {str(e)[:100]}",
            parse_mode="HTML"
        )


async def cmd_arb(message: Message):
    """Handle /arb command - show arbitrage opportunities."""
    await message.answer("⚡ <b>Ищу арбитраж...</b>", parse_mode="HTML")

    try:
        deals = giftasset_cache.get_best_deals(limit=20)

        # Filter only deals with significant arbitrage
        arb_deals = [d for d in deals if d.discount_pct and d.discount_pct >= 15]

        if not arb_deals:
            await message.answer(
                "🤷 Сейчас нет явных арбитражных возможностей (дисконт &lt;15%).\n"
                "Попробуй позже или смотри /deals для всех сделок.",
                parse_mode="HTML"
            )
            return

        lines = []
        lines.append("⚡ <b>АРБИТРАЖНЫЕ ВОЗМОЖНОСТИ</b>")
        lines.append("<i>Подарки дешевле чем на других маркетах</i>")
        lines.append("")

        for i, deal in enumerate(arb_deals[:10], 1):
            lines.append(f"<b>{i}. {deal.gift_name}</b>")
            lines.append(f"   💰 {deal.price:.1f} TON на {deal.provider.upper()}")
            lines.append(f"   📉 <b>-{deal.discount_pct:.0f}%</b> от avg floor ({deal.market_floor.avg_floor:.1f} TON)")

            # Show other provider prices
            other_prices = []
            for prov, pf in deal.market_floor.providers.items():
                if prov.lower() != deal.provider.lower() and pf.model_floor:
                    other_prices.append(f"{prov}: {pf.model_floor:.0f}")
            if other_prices:
                lines.append(f"   🏪 Другие: {' | '.join(other_prices[:3])}")

            lines.append("")

        await message.answer("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in /arb: {e}", exc_info=True)
        await message.answer(
            f"❌ Ошибка: {str(e)[:100]}",
            parse_mode="HTML"
        )
