"""Telegram gift statistics service using MTProto API."""

import logging
import time
import asyncio
import aiohttp
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from telethon.tl.functions.payments import (
    GetUniqueStarGiftRequest,
    GetUniqueStarGiftValueInfoRequest,
)

from src.services.telegram_client import tg_client_manager

logger = logging.getLogger(__name__)


# Currency conversion with real-time rates
class CurrencyConverter:
    """Real-time currency conversion using CoinGecko API."""

    def __init__(self):
        self._ton_usd_rate: Optional[Decimal] = None
        self._usd_cad_rate: Optional[Decimal] = None
        self._rate_timestamp: float = 0
        self._rate_ttl = 300  # 5 minutes cache

    async def get_ton_usd_rate(self) -> Decimal:
        """Get current TON/USD rate."""
        await self._refresh_rates_if_needed()
        return self._ton_usd_rate or Decimal("3.2")  # Fallback

    async def get_usd_cad_rate(self) -> Decimal:
        """Get current USD/CAD rate."""
        await self._refresh_rates_if_needed()
        return self._usd_cad_rate or Decimal("1.36")  # Fallback

    async def _refresh_rates_if_needed(self):
        """Refresh rates if cache expired."""
        if time.time() - self._rate_timestamp < self._rate_ttl:
            return

        try:
            async with aiohttp.ClientSession() as session:
                # Get TON price in USD and CAD from CoinGecko
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {
                    "ids": "the-open-network",
                    "vs_currencies": "usd,cad"
                }
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ton_data = data.get("the-open-network", {})
                        ton_usd = ton_data.get("usd")
                        ton_cad = ton_data.get("cad")

                        if ton_usd:
                            self._ton_usd_rate = Decimal(str(ton_usd))
                        if ton_cad and ton_usd:
                            self._usd_cad_rate = Decimal(str(ton_cad)) / Decimal(str(ton_usd))

                        self._rate_timestamp = time.time()
                        logger.info(
                            f"Updated TON rates: 1 TON = ${self._ton_usd_rate} USD, "
                            f"USD/CAD = {self._usd_cad_rate}"
                        )
                    else:
                        logger.warning(f"CoinGecko API error: {resp.status}")

        except Exception as e:
            logger.error(f"Failed to fetch currency rates: {e}")

    async def usd_to_ton(self, usd_amount: Decimal) -> Decimal:
        """Convert USD to TON."""
        rate = await self.get_ton_usd_rate()
        return round(usd_amount / rate, 2)

    async def cad_to_ton(self, cad_amount: Decimal) -> Decimal:
        """Convert CAD to TON."""
        usd_cad = await self.get_usd_cad_rate()
        usd_amount = cad_amount / usd_cad
        return await self.usd_to_ton(usd_amount)

    async def to_ton(self, amount: Decimal, currency: str) -> Optional[Decimal]:
        """Convert amount to TON based on currency."""
        if currency == "USD":
            return await self.usd_to_ton(amount)
        elif currency == "CAD":
            return await self.cad_to_ton(amount)
        return None


# Global converter instance
currency_converter = CurrencyConverter()


@dataclass
class GiftStats:
    """Статистика подарка из Telegram."""

    slug: str
    title: str = ""

    # Цены в оригинальной валюте (центы)
    floor_price_cents: Optional[int] = None
    average_price_cents: Optional[int] = None
    initial_price_cents: Optional[int] = None
    value_cents: Optional[int] = None
    currency: str = "CAD"

    # Информация о рынке
    listed_count: int = 0
    fragment_listed_count: int = 0

    # Кэшированные цены в TON (заполняются асинхронно)
    _floor_price_ton: Optional[Decimal] = None
    _average_price_ton: Optional[Decimal] = None
    _estimated_max_price_ton: Optional[Decimal] = None

    @property
    def floor_price(self) -> Optional[Decimal]:
        """Минимальная цена в валюте (доллары)."""
        if self.floor_price_cents:
            return Decimal(self.floor_price_cents) / Decimal("100")
        return None

    @property
    def average_price(self) -> Optional[Decimal]:
        """Средняя цена в валюте (доллары)."""
        if self.average_price_cents:
            return Decimal(self.average_price_cents) / Decimal("100")
        return None

    @property
    def estimated_max_price(self) -> Optional[Decimal]:
        """Расчётная максимальная цена.

        Формула: max ≈ average + (average - floor) * 2
        """
        if self.average_price and self.floor_price:
            spread = self.average_price - self.floor_price
            return round(self.average_price + spread * Decimal("2"), 2)
        return None

    @property
    def floor_price_ton(self) -> Optional[Decimal]:
        """Минимальная цена в TON (из кэша)."""
        return self._floor_price_ton

    @property
    def average_price_ton(self) -> Optional[Decimal]:
        """Средняя цена в TON (из кэша)."""
        return self._average_price_ton

    @property
    def estimated_max_price_ton(self) -> Optional[Decimal]:
        """Расчётная максимальная цена в TON (из кэша)."""
        return self._estimated_max_price_ton

    async def calculate_ton_prices(self):
        """Рассчитать цены в TON используя актуальный курс."""
        if self.floor_price:
            self._floor_price_ton = await currency_converter.to_ton(
                self.floor_price, self.currency
            )
        if self.average_price:
            self._average_price_ton = await currency_converter.to_ton(
                self.average_price, self.currency
            )
        if self.estimated_max_price:
            self._estimated_max_price_ton = await currency_converter.to_ton(
                self.estimated_max_price, self.currency
            )


class TelegramStatsService:
    """Service for fetching gift statistics from Telegram MTProto API."""

    def __init__(self):
        # Cache to avoid hitting API too often
        self._cache: dict[str, tuple[GiftStats, float]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def get_gift_stats(self, slug: str) -> Optional[GiftStats]:
        """Get statistics for a gift by slug.

        Args:
            slug: Gift slug (e.g., "icecream-172405")

        Returns:
            GiftStats with floor_price, average_price, etc.
        """
        # Check cache first (without lock)
        if slug in self._cache:
            stats, timestamp = self._cache[slug]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Cache hit for {slug}")
                return stats

        # Use shared lock for Telegram API calls to avoid SQLite "database is locked" errors
        async with tg_client_manager.lock:
            # Double-check cache after acquiring lock
            if slug in self._cache:
                stats, timestamp = self._cache[slug]
                if time.time() - timestamp < self._cache_ttl:
                    return stats

            client = await tg_client_manager.get_client()
            if not client:
                return None

            try:
                # Get basic gift info
                gift_result = await client(GetUniqueStarGiftRequest(slug=slug))

                if not gift_result or not gift_result.gift:
                    logger.warning(f"No gift data for slug: {slug}")
                    return None

                gift = gift_result.gift

                # Get value info (floor, average, etc.)
                value_info = await client(GetUniqueStarGiftValueInfoRequest(slug=slug))

                if not value_info:
                    logger.warning(f"No value info for slug: {slug}")
                    return None

                # Build stats object
                stats = GiftStats(
                    slug=slug,
                    title=gift.title,
                    floor_price_cents=getattr(value_info, 'floor_price', None),
                    average_price_cents=getattr(value_info, 'average_price', None),
                    initial_price_cents=getattr(value_info, 'initial_sale_price', None),
                    value_cents=getattr(value_info, 'value', None),
                    currency=getattr(value_info, 'currency', 'CAD'),
                    listed_count=getattr(value_info, 'listed_count', 0) or 0,
                    fragment_listed_count=getattr(value_info, 'fragment_listed_count', 0) or 0,
                )

                # Рассчитать цены в TON по актуальному курсу
                await stats.calculate_ton_prices()

                # Cache result
                self._cache[slug] = (stats, time.time())

                logger.debug(
                    f"Gift stats for {slug}: floor={stats.floor_price} {stats.currency}, "
                    f"avg={stats.average_price} {stats.currency}, "
                    f"floor_ton={stats.floor_price_ton}, avg_ton={stats.average_price_ton}"
                )

                return stats

            except Exception as e:
                logger.error(f"Error fetching gift stats for {slug}: {e}")
                return None

    async def get_reference_price_ton(self, slug: str) -> Optional[Decimal]:
        """Get reference price in TON for profit calculation.

        Uses average_price from Telegram as the reference.
        """
        stats = await self.get_gift_stats(slug)
        if stats and stats.average_price_ton:
            return stats.average_price_ton
        return None

    async def get_floor_price_ton(self, slug: str) -> Optional[Decimal]:
        """Get floor price in TON."""
        stats = await self.get_gift_stats(slug)
        if stats and stats.floor_price_ton:
            return stats.floor_price_ton
        return None


# Global instance
telegram_stats = TelegramStatsService()
