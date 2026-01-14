"""Analytics engine for calculating ARP, liquidity, confidence."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
import numpy as np
from src.core.models import (
    AssetAnalytics,
    ConfidenceLevel,
    Trend,
    FloorData,
    BLACK_PACK_BACKGROUNDS,
)
from src.storage.postgres import db
from src.storage.redis_client import redis_client
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AnalyticsEngine:
    """Calculate analytics for assets."""

    def __init__(self):
        self.floor_cache_ttl = 30  # 30 seconds
        self.analytics_cache_ttl = 60  # 60 seconds

    async def calculate_analytics(
        self, asset_key: str, force_refresh: bool = False
    ) -> Optional[AssetAnalytics]:
        """Calculate or retrieve cached analytics for an asset."""
        # Check cache first
        if not force_refresh:
            cached = await redis_client.get_json(f"analytics:{asset_key}")
            if cached:
                logger.debug(f"Analytics cache hit: {asset_key}")
                return AssetAnalytics(**cached)

        logger.info(f"Calculating analytics for {asset_key}")

        # Parse asset_key
        parts = asset_key.split(":")
        if len(parts) < 2:
            logger.error(f"Invalid asset_key format: {asset_key}")
            return None

        model = parts[0]
        backdrop = parts[1] if parts[1] != "no_bg" else None

        # Get active listings
        listings = await self._get_active_listings(model, backdrop)

        # Calculate floors
        floors = self._calculate_floors(listings)

        # Get sales data
        sales_7d = await self._get_sales(model, backdrop, days=7)
        sales_30d = await self._get_sales(model, backdrop, days=30)

        # Calculate quantiles
        quantiles = self._calculate_quantiles(sales_7d)

        # Calculate liquidity score
        liquidity = self._calculate_liquidity_score(
            sales_7d=len(sales_7d),
            sales_30d=len(sales_30d),
            listings_count=len(listings),
            last_sale=sales_7d[0] if sales_7d else None,
        )

        # Determine confidence level
        confidence = self._determine_confidence(
            sales_7d=len(sales_7d),
            sales_30d=len(sales_30d),
            liquidity=liquidity,
            listings_count=len(listings),
        )

        # Calculate trend
        trend = self._calculate_trend(sales_7d)

        # Get last sale time
        last_sale_at = sales_7d[0]["event_time"] if sales_7d else None

        # Create analytics object
        analytics = AssetAnalytics(
            asset_key=asset_key,
            floor_1st=floors.first,
            floor_2nd=floors.second,
            floor_3rd=floors.third,
            listings_count=len(listings),
            sales_7d=len(sales_7d),
            sales_30d=len(sales_30d),
            price_q25=quantiles.get("q25"),
            price_q50=quantiles.get("q50"),
            price_q75=quantiles.get("q75"),
            price_max=quantiles.get("max"),
            liquidity_score=liquidity,
            confidence_level=confidence,
            last_sale_at=last_sale_at,
            trend=trend,
            updated_at=datetime.utcnow(),
        )

        # Cache analytics
        await redis_client.set_json(
            f"analytics:{asset_key}", analytics.model_dump(), ttl=self.analytics_cache_ttl
        )

        # Save to database
        await self._save_analytics(analytics)

        return analytics

    async def _get_active_listings(
        self, model: str, backdrop: Optional[str]
    ) -> List[Dict]:
        """Get active listings for model and backdrop."""
        async for session in db.get_session():
            if backdrop:
                query = text("""
                SELECT price FROM active_listings
                WHERE model = :model AND backdrop = :backdrop
                ORDER BY price ASC
                """)
                result = await session.execute(query, {"model": model, "backdrop": backdrop})
            else:
                query = text("""
                SELECT price FROM active_listings
                WHERE model = :model AND backdrop IS NULL
                ORDER BY price ASC
                """)
                result = await session.execute(query, {"model": model})

            rows = result.fetchall()
            return [{"price": Decimal(str(row[0]))} for row in rows]

        return []

    def _calculate_floors(self, listings: List[Dict]) -> FloorData:
        """Calculate 1st, 2nd, 3rd floor prices."""
        if not listings:
            return FloorData(count=0)

        prices = [listing["price"] for listing in listings]
        prices.sort()

        return FloorData(
            first=prices[0] if len(prices) >= 1 else None,
            second=prices[1] if len(prices) >= 2 else None,
            third=prices[2] if len(prices) >= 3 else None,
            count=len(prices),
        )

    async def _get_sales(
        self, model: str, backdrop: Optional[str], days: int = 7
    ) -> List[Dict]:
        """Get buy events (sales) for model and backdrop."""
        since = datetime.utcnow() - timedelta(days=days)

        async for session in db.get_session():
            if backdrop:
                query = text("""
                SELECT event_time, price FROM market_events
                WHERE event_type = 'buy' AND model = :model AND backdrop = :backdrop
                AND event_time >= :since
                ORDER BY event_time DESC
                """)
                result = await session.execute(
                    query, {"model": model, "backdrop": backdrop, "since": since}
                )
            else:
                query = text("""
                SELECT event_time, price FROM market_events
                WHERE event_type = 'buy' AND model = :model AND backdrop IS NULL
                AND event_time >= :since
                ORDER BY event_time DESC
                """)
                result = await session.execute(query, {"model": model, "since": since})

            rows = result.fetchall()
            return [
                {"event_time": row[0], "price": Decimal(str(row[1]))} for row in rows
            ]

        return []

    def _calculate_quantiles(self, sales: List[Dict]) -> Dict[str, Optional[Decimal]]:
        """Calculate price quantiles from sales."""
        if not sales:
            return {"q25": None, "q50": None, "q75": None, "max": None}

        prices = [float(sale["price"]) for sale in sales]

        if len(prices) < 2:
            return {
                "q25": Decimal(str(prices[0])),
                "q50": Decimal(str(prices[0])),
                "q75": Decimal(str(prices[0])),
                "max": Decimal(str(prices[0])),
            }

        q25, q50, q75 = np.percentile(prices, [25, 50, 75])

        return {
            "q25": Decimal(str(round(q25, 2))),
            "q50": Decimal(str(round(q50, 2))),
            "q75": Decimal(str(round(q75, 2))),
            "max": Decimal(str(round(max(prices), 2))),
        }

    def _calculate_liquidity_score(
        self,
        sales_7d: int,
        sales_30d: int,
        listings_count: int,
        last_sale: Optional[Dict],
    ) -> Decimal:
        """Calculate liquidity score (0-10)."""
        score = 0.0

        # Sales in last 7 days (weight: 2.0)
        score += min(sales_7d * 2.0, 10.0)

        # Listings count (weight: 0.5)
        score += min(listings_count * 0.5, 5.0)

        # Recent sale bonus (weight: 2.0)
        if last_sale:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            event_time = last_sale["event_time"]
            if event_time.tzinfo is None:
                # Make naive datetime aware
                event_time = event_time.replace(tzinfo=timezone.utc)
            hours_since = (now - event_time).total_seconds() / 3600
            if hours_since < 24:
                score += 2.0
            elif hours_since < 72:
                score += 1.0

        # Sales 30d context (weight: 0.5)
        if sales_30d >= 15:
            score += 1.0
        elif sales_30d >= 8:
            score += 0.5

        return Decimal(str(round(min(score, 10.0), 1)))

    def _determine_confidence(
        self, sales_7d: int, sales_30d: int, liquidity: Decimal, listings_count: int
    ) -> ConfidenceLevel:
        """Determine confidence level based on data quality."""
        # Very High: много продаж, высокая ликвидность, много листингов
        if sales_7d >= 10 and liquidity >= 7 and listings_count >= 5:
            return ConfidenceLevel.VERY_HIGH

        # High: достаточно продаж, средняя ликвидность
        if (sales_7d >= 5 or (sales_30d >= 15 and sales_7d >= 2)) and liquidity >= 5:
            return ConfidenceLevel.HIGH

        # Medium: есть данные, но ограниченные
        if (sales_7d >= 2 or sales_30d >= 8) and liquidity >= 3:
            return ConfidenceLevel.MEDIUM

        # Low: мало данных
        return ConfidenceLevel.LOW

    def _calculate_trend(self, sales: List[Dict]) -> Optional[Trend]:
        """Calculate price trend from recent sales."""
        if len(sales) < 3:
            return Trend.STABLE

        # Take last 10 sales
        recent_sales = sales[:10]
        prices = [float(sale["price"]) for sale in recent_sales]

        # Simple linear regression to detect trend
        x = np.arange(len(prices))
        slope = np.polyfit(x, prices, 1)[0]

        # Trend thresholds
        if slope > 0.5:  # Rising
            return Trend.RISING
        elif slope < -0.5:  # Falling
            return Trend.FALLING
        else:
            return Trend.STABLE

    async def _save_analytics(self, analytics: AssetAnalytics):
        """Save analytics to database."""
        async for session in db.get_session():
            query = text("""
            INSERT INTO asset_analytics
            (asset_key, floor_1st, floor_2nd, floor_3rd, listings_count,
             sales_7d, sales_30d, price_q25, price_q50, price_q75, price_max,
             liquidity_score, confidence_level, last_sale_at, trend, updated_at)
            VALUES (:asset_key, :floor_1st, :floor_2nd, :floor_3rd, :listings_count,
                    :sales_7d, :sales_30d, :price_q25, :price_q50, :price_q75, :price_max,
                    :liquidity_score, :confidence_level, :last_sale_at, :trend, :updated_at)
            ON CONFLICT (asset_key)
            DO UPDATE SET
                floor_1st = EXCLUDED.floor_1st,
                floor_2nd = EXCLUDED.floor_2nd,
                floor_3rd = EXCLUDED.floor_3rd,
                listings_count = EXCLUDED.listings_count,
                sales_7d = EXCLUDED.sales_7d,
                sales_30d = EXCLUDED.sales_30d,
                price_q25 = EXCLUDED.price_q25,
                price_q50 = EXCLUDED.price_q50,
                price_q75 = EXCLUDED.price_q75,
                price_max = EXCLUDED.price_max,
                liquidity_score = EXCLUDED.liquidity_score,
                confidence_level = EXCLUDED.confidence_level,
                last_sale_at = EXCLUDED.last_sale_at,
                trend = EXCLUDED.trend,
                updated_at = EXCLUDED.updated_at
            """)

            await session.execute(
                query,
                {
                    "asset_key": analytics.asset_key,
                    "floor_1st": float(analytics.floor_1st) if analytics.floor_1st else None,
                    "floor_2nd": float(analytics.floor_2nd) if analytics.floor_2nd else None,
                    "floor_3rd": float(analytics.floor_3rd) if analytics.floor_3rd else None,
                    "listings_count": analytics.listings_count,
                    "sales_7d": analytics.sales_7d,
                    "sales_30d": analytics.sales_30d,
                    "price_q25": float(analytics.price_q25) if analytics.price_q25 else None,
                    "price_q50": float(analytics.price_q50) if analytics.price_q50 else None,
                    "price_q75": float(analytics.price_q75) if analytics.price_q75 else None,
                    "price_max": float(analytics.price_max) if analytics.price_max else None,
                    "liquidity_score": (
                        float(analytics.liquidity_score) if analytics.liquidity_score else None
                    ),
                    "confidence_level": (
                        analytics.confidence_level.value if analytics.confidence_level else None
                    ),
                    "last_sale_at": analytics.last_sale_at,
                    "trend": analytics.trend.value if analytics.trend else None,
                    "updated_at": analytics.updated_at,
                },
            )

            await session.commit()

    async def calculate_arp(
        self, analytics: AssetAnalytics, background_filter: str = "general"
    ) -> Optional[Decimal]:
        """Calculate Adaptive Reference Price (ARP)."""
        if not analytics:
            return None

        # Floor component weight
        floor_weight = 0.4 if analytics.liquidity_score and analytics.liquidity_score >= 5 else 0.6

        # Sales component weight
        sales_weight = 1.0 - floor_weight

        # Calculate floor component
        floor_component = None
        if analytics.floor_2nd:
            floor_component = analytics.floor_2nd
        elif analytics.floor_1st:
            # Fallback: если только 1 листинг, применяем консервативный множитель
            floor_component = analytics.floor_1st * Decimal("1.20")
        elif analytics.listings_count == 0 and analytics.price_q50:
            # Fallback: если нет листингов, используем медиану продаж
            floor_component = analytics.price_q50 * Decimal("1.10")

        # Calculate sales component
        sales_component = analytics.price_q50 if analytics.price_q50 else None

        # Combine components
        if floor_component and sales_component:
            arp = (floor_component * Decimal(str(floor_weight))) + (
                sales_component * Decimal(str(sales_weight))
            )
        elif floor_component:
            arp = floor_component
        elif sales_component:
            arp = sales_component
        else:
            return None

        # Apply liquidity penalty
        if analytics.liquidity_score:
            if analytics.liquidity_score < 3:
                arp *= Decimal("1.5")  # Требуем больший дисконт
            elif analytics.liquidity_score < 5:
                arp *= Decimal("1.2")

        # Apply momentum adjustment
        if analytics.trend == Trend.FALLING:
            arp *= Decimal("0.95")  # Ждём ещё
        elif analytics.trend == Trend.RISING:
            arp *= Decimal("1.05")  # Рынок разогревается

        return round(arp, 2)

    async def calculate_hotness(
        self, asset_key: str, analytics: AssetAnalytics
    ) -> Decimal:
        """Calculate hotness score (0-10) based on recent activity."""
        score = 0.0

        # Recent buys in last hour (weight: 5.0)
        recent_buys = await self._get_recent_buys_count(asset_key, hours=1)
        score += min(recent_buys * 5.0, 25.0)

        # Price momentum (weight: 2.0)
        if analytics.trend == Trend.FALLING:
            score += 10.0  # Падение = возможность
        elif analytics.trend == Trend.RISING:
            score += 5.0  # Рост = интерес

        # Liquidity (weight: 1.0)
        if analytics.liquidity_score:
            score += float(analytics.liquidity_score) * 1.0

        # Check if new listing (weight: 3.0)
        is_new = await self._is_new_listing(asset_key, minutes=5)
        if is_new:
            score += 15.0

        return Decimal(str(round(min(score / 5.0, 10.0), 1)))

    async def _get_recent_buys_count(self, asset_key: str, hours: int = 1) -> int:
        """Get count of buy events in last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        parts = asset_key.split(":")
        model = parts[0]
        backdrop = parts[1] if parts[1] != "no_bg" else None

        async for session in db.get_session():
            if backdrop:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'buy' AND model = :model AND backdrop = :backdrop
                AND event_time >= :since
                """)
                result = await session.execute(
                    query, {"model": model, "backdrop": backdrop, "since": since}
                )
            else:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'buy' AND model = :model AND backdrop IS NULL
                AND event_time >= :since
                """)
                result = await session.execute(query, {"model": model, "since": since})

            return result.scalar() or 0

        return 0

    async def _is_new_listing(self, asset_key: str, minutes: int = 5) -> bool:
        """Check if there was a listing event in last N minutes."""
        since = datetime.utcnow() - timedelta(minutes=minutes)
        parts = asset_key.split(":")
        model = parts[0]
        backdrop = parts[1] if parts[1] != "no_bg" else None

        async for session in db.get_session():
            if backdrop:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'listing' AND model = :model AND backdrop = :backdrop
                AND event_time >= :since
                """)
                result = await session.execute(
                    query, {"model": model, "backdrop": backdrop, "since": since}
                )
            else:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'listing' AND model = :model AND backdrop IS NULL
                AND event_time >= :since
                """)
                result = await session.execute(query, {"model": model, "since": since})

            return (result.scalar() or 0) > 0

        return False


# Global analytics engine
analytics_engine = AnalyticsEngine()
