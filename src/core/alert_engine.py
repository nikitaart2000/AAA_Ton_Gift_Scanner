"""Alert engine for filtering, ranking, and cooldown management."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List
from src.core.models import (
    MarketEvent,
    EventType,
    Alert,
    UserSettings,
    AssetAnalytics,
    ConfidenceLevel,
    AlertMode,
    BackgroundFilter,
    BLACK_PACK_BACKGROUNDS,
)
from src.core.analytics import analytics_engine
from src.storage.postgres import db
from src.storage.redis_client import redis_client
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AlertEngine:
    """Engine for evaluating deals and generating alerts."""

    def __init__(self):
        self.cooldown_seconds = 120  # 2 minutes per asset
        self.max_alerts_per_hour = 50
        self.batch_window_seconds = 30

    async def evaluate_event(
        self, event: MarketEvent, user_settings: UserSettings
    ) -> Optional[Alert]:
        """Evaluate if event should trigger an alert."""
        # Only evaluate listing and change_price events
        if event.event_type not in [EventType.LISTING, EventType.CHANGE_PRICE]:
            return None

        logger.debug(f"Evaluating event: {event.asset_key}")

        # Check if muted
        if await self.check_muted(user_settings.user_id, event.asset_key):
            logger.debug(f"Asset is muted: {event.asset_key}")
            return None

        # Check basic filters
        if not await self._passes_basic_filters(event, user_settings):
            logger.debug(f"Event failed basic filters: {event.asset_key}")
            return None

        # Get analytics
        analytics = await analytics_engine.calculate_analytics(event.asset_key)
        if not analytics:
            logger.debug(f"No analytics available: {event.asset_key}")
            return None

        # Calculate ARP and profit
        arp = await analytics_engine.calculate_arp(
            analytics, background_filter=user_settings.background_filter
        )
        if not arp or arp <= 0:
            logger.debug(f"Invalid ARP: {event.asset_key}")
            return None

        profit_pct = ((arp - event.price) / arp) * 100

        # Filter out very low quality deals
        # Если только 1 листинг (нет 2го флора) + LOW confidence + низкая ликвидность
        if analytics.listings_count == 1 and analytics.confidence_level == ConfidenceLevel.LOW:
            # Требуем ОЧЕНЬ высокий profit для компенсации неопределённости
            if profit_pct < 50:
                logger.debug(
                    f"Single listing + LOW confidence rejected: profit={profit_pct:.1f}% < 50%"
                )
                return None

        # Filter out very low quality deals (low liquidity + low confidence)
        if (
            analytics.liquidity_score
            and analytics.liquidity_score < 2
            and analytics.confidence_level == ConfidenceLevel.LOW
        ):
            # Для очень неликвидных активов с LOW confidence требуем минимум 35% profit
            if profit_pct < 35:
                logger.debug(
                    f"Low quality deal rejected: liquidity={analytics.liquidity_score}, "
                    f"confidence=LOW, profit={profit_pct:.1f}%"
                )
                return None

        # Check profit threshold (with liquidity penalty)
        min_profit = user_settings.profit_min
        if analytics.liquidity_score and analytics.liquidity_score < 5:
            min_profit *= Decimal("1.2")  # Требуем больший дисконт для неликвида

        if profit_pct < min_profit:
            logger.debug(
                f"Profit too low: {profit_pct:.1f}% < {min_profit}% for {event.asset_key}"
            )
            return None

        # Anti-false-positive checks
        if not await self._passes_anti_fp_checks(event, analytics, profit_pct):
            logger.debug(f"Failed anti-FP checks: {event.asset_key}")
            return None

        # Calculate hotness
        hotness = await analytics_engine.calculate_hotness(event.asset_key, analytics)

        # Check mode-specific thresholds
        if user_settings.mode == AlertMode.SNIPER:
            # Sniper mode: more strict
            if analytics.confidence_level == ConfidenceLevel.LOW:
                if profit_pct < 30:
                    return None
            elif analytics.confidence_level == ConfidenceLevel.MEDIUM:
                if profit_pct < 20:
                    return None
            elif profit_pct < 15 and hotness < 8:
                return None

        # Check cooldown
        if await self._is_on_cooldown(user_settings.user_id, event.asset_key):
            logger.debug(f"Asset on cooldown: {event.asset_key}")
            return None

        # Check rate limit
        if await self._is_rate_limited(user_settings.user_id):
            logger.warning(f"User {user_settings.user_id} is rate limited")
            return None

        # Get reference prices for context
        floor_black_pack = None
        floor_general = analytics.floor_2nd

        if event.backdrop in BLACK_PACK_BACKGROUNDS:
            floor_black_pack = analytics.floor_2nd

        # Determine reference type
        reference_type = self._get_reference_type(user_settings, event)

        # Create alert
        alert = Alert(
            asset_key=event.asset_key,
            gift_id=event.gift_id,
            gift_name=event.gift_name,
            model=event.model,
            backdrop=event.backdrop,
            number=event.number,
            price=event.price,
            profit_pct=round(profit_pct, 1),
            reference_price=arp,
            reference_type=reference_type,
            hotness=hotness,
            liquidity_score=analytics.liquidity_score or Decimal("0"),
            confidence_level=analytics.confidence_level or ConfidenceLevel.LOW,
            floor_black_pack=floor_black_pack,
            floor_general=floor_general,
            sales_q25=analytics.price_q25,
            sales_q75=analytics.price_q75,
            sales_max=analytics.price_max,
            sales_48h=await self._get_sales_count(event.asset_key, hours=48),
            is_priority=hotness >= 7 or profit_pct >= 25,
            photo_url=event.photo_url,
            event_time=event.event_time,
            timestamp=datetime.now(timezone.utc),
            source=event.source,
            event_type=event.event_type,
        )

        # Set cooldown
        await self._set_cooldown(user_settings.user_id, event.asset_key)

        # Increment rate limit counter
        await self._increment_rate_limit(user_settings.user_id)

        logger.info(
            f"✅ Alert generated: {event.asset_key} | Profit: {profit_pct:.1f}% | "
            f"Hotness: {hotness}/10 | Priority: {alert.is_priority}"
        )

        return alert

    async def _passes_basic_filters(
        self, event: MarketEvent, settings: UserSettings
    ) -> bool:
        """Check if event passes basic filters."""
        # Price range
        if settings.price_min and event.price < settings.price_min:
            return False
        if settings.price_max and event.price > settings.price_max:
            return False

        # Background filter
        if settings.background_filter == BackgroundFilter.NONE:
            if event.backdrop is not None:
                return False
        elif settings.background_filter == BackgroundFilter.BLACK_PACK:
            if event.backdrop not in BLACK_PACK_BACKGROUNDS:
                return False

        # Clean only
        if settings.clean_only:
            # TODO: Implement clean/dirty detection
            pass

        return True

    async def _passes_anti_fp_checks(
        self, event: MarketEvent, analytics: AssetAnalytics, profit_pct: Decimal
    ) -> bool:
        """Anti-false-positive checks."""
        # Too good to be true?
        if profit_pct > 70 and analytics.liquidity_score and analytics.liquidity_score < 4:
            logger.warning(
                f"Suspicious deal: {profit_pct:.1f}% profit on illiquid asset {event.asset_key}"
            )
            return False

        # Stale listing check (listing older than 6 hours)
        if event.event_type == EventType.LISTING:
            if event.event_time:
                now = datetime.now(timezone.utc)
                event_time = event.event_time
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                age_hours = (now - event_time).total_seconds() / 3600
                if age_hours > 6:
                    logger.debug(f"Stale listing: {age_hours:.1f}h old")
                    return False

        # Rapid price changes (manipulation detection)
        if event.event_type == EventType.CHANGE_PRICE:
            recent_changes = await self._get_recent_change_count(event.asset_key, hours=1)
            if recent_changes >= 3:
                logger.warning(
                    f"Too many price changes: {recent_changes} in 1h for {event.asset_key}"
                )
                return False

        # Black pack validation
        if event.backdrop in BLACK_PACK_BACKGROUNDS:
            # Ensure there are at least 2 listings in black pack for reliable floor
            if analytics.listings_count < 2:
                logger.debug(
                    f"Insufficient black pack listings: {analytics.listings_count}"
                )
                # Lower confidence but don't reject
                pass

        return True

    def _get_reference_type(self, settings: UserSettings, event: MarketEvent) -> str:
        """Get human-readable reference type."""
        if settings.background_filter == BackgroundFilter.BLACK_PACK:
            return "2nd floor black_pack"
        elif settings.background_filter == BackgroundFilter.NONE:
            return "2nd floor no_bg"
        else:
            return "2nd floor general"

    async def _is_on_cooldown(self, user_id: int, asset_key: str) -> bool:
        """Check if asset is on cooldown for user."""
        key = f"cooldown:user:{user_id}:asset:{asset_key}"
        return await redis_client.exists(key)

    async def _set_cooldown(self, user_id: int, asset_key: str):
        """Set cooldown for asset."""
        key = f"cooldown:user:{user_id}:asset:{asset_key}"
        await redis_client.set(key, "1", ttl=self.cooldown_seconds)

    async def _is_rate_limited(self, user_id: int) -> bool:
        """Check if user has exceeded rate limit."""
        key = f"ratelimit:alerts:{user_id}:1h"
        count = await redis_client.get(key)
        if count:
            return int(count) >= self.max_alerts_per_hour
        return False

    async def _increment_rate_limit(self, user_id: int):
        """Increment rate limit counter."""
        key = f"ratelimit:alerts:{user_id}:1h"
        count = await redis_client.incr(key)
        if count == 1:
            # Set expiration on first increment
            await redis_client.expire(key, 3600)

    async def _get_sales_count(self, asset_key: str, hours: int = 48) -> int:
        """Get sales count in last N hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
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

    async def _get_recent_change_count(self, asset_key: str, hours: int = 1) -> int:
        """Get count of change_price events in last N hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        parts = asset_key.split(":")
        model = parts[0]
        backdrop = parts[1] if parts[1] != "no_bg" else None

        async for session in db.get_session():
            if backdrop:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'change_price' AND model = :model AND backdrop = :backdrop
                AND event_time >= :since
                """)
                result = await session.execute(
                    query, {"model": model, "backdrop": backdrop, "since": since}
                )
            else:
                query = text("""
                SELECT COUNT(*) FROM market_events
                WHERE event_type = 'change_price' AND model = :model AND backdrop IS NULL
                AND event_time >= :since
                """)
                result = await session.execute(query, {"model": model, "since": since})

            return result.scalar() or 0

        return 0

    async def check_muted(self, user_id: int, asset_key: str) -> bool:
        """Check if asset is muted for user."""
        async for session in db.get_session():
            query = text("""
            SELECT COUNT(*) FROM muted_assets
            WHERE user_id = :user_id AND asset_key = :asset_key
            AND muted_until > NOW()
            """)
            result = await session.execute(
                query, {"user_id": user_id, "asset_key": asset_key}
            )
            return (result.scalar() or 0) > 0

        return False


# Global alert engine
alert_engine = AlertEngine()
