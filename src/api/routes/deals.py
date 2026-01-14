"""API routes for deals - REAL DATA FROM DB."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Query, Depends

from src.api.models import DealCard, DealsFeedResponse, MarketOverview
from src.core.models import (
    ConfidenceLevel,
    EventType,
    EventSource,
    Trend,
    BLACK_PACK_BACKGROUNDS,
)
from src.storage.db_pool import get_db_pool, DatabasePool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deals", tags=["deals"])


def _compute_quality_badge(
    profit_pct: float,
    liquidity_score: float,
    confidence_level: str,
    hotness: float,
    is_black_pack: bool,
) -> Optional[str]:
    """Вычислить качество дила - BADGE."""
    if is_black_pack:
        return "BLACK_PACK"

    if hotness >= 7:
        return "HOT"

    # GEM: высокая ликвидность + хороший профит
    if liquidity_score >= 5 and profit_pct >= 20 and confidence_level in ['high', 'very_high']:
        return "GEM"

    # SNIPER: идеальная комбинация
    if profit_pct >= 25 and liquidity_score >= 7 and confidence_level == 'very_high' and hotness >= 6:
        return "SNIPER"

    return None


@router.get("/feed", response_model=DealsFeedResponse)
async def get_deals_feed(
    page: int = Query(0, ge=0),
    page_size: int = Query(50, ge=1, le=100),
    sort_by: str = Query("smart", regex="^(smart|profit|hotness|time|liquidity)$"),
    min_profit: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    black_pack_only: bool = Query(False),
    priority_only: bool = Query(False),
    db: DatabasePool = Depends(get_db_pool),
) -> DealsFeedResponse:
    """
    Получить фид сделок из БД.

    Smart sorting: (profit * 0.4) + (liquidity * 3.0) + (confidence * 0.2) + (hotness * 0.1)
    """

    # Временное окно: последние 24 часа (чтобы показывать все дилы)
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=24)

    logger.info(f"get_deals_feed: min_profit={min_profit}, type={type(min_profit)}")

    # Фильтры
    filters = ["me.event_time >= $1", "me.event_type IN ('listing', 'change_price')"]
    params = [time_threshold]
    param_idx = 2

    # NOTE: min_profit фильтр применяется в CTE после вычисления profit_pct, не здесь

    if max_price is not None:
        filters.append(f"me.price <= ${param_idx}")
        params.append(max_price)
        param_idx += 1

    if black_pack_only:
        filters.append(f"me.backdrop = ANY(${param_idx})")
        params.append(list(BLACK_PACK_BACKGROUNDS))
        param_idx += 1

    where_clause = " AND ".join(filters)

    # Сортировка
    if sort_by == "smart":
        order_clause = """
            (
                (COALESCE(le.profit_pct, 0) * 0.4) +
                (COALESCE(le.liquidity_score, 0) * 3.0) +
                (CASE
                    WHEN le.confidence_level = 'very_high' THEN 10
                    WHEN le.confidence_level = 'high' THEN 7
                    WHEN le.confidence_level = 'medium' THEN 4
                    ELSE 1
                END * 0.2) +
                (COALESCE(le.hotness, 0) * 0.1)
            ) DESC
        """
    elif sort_by == "profit":
        order_clause = "le.profit_pct DESC NULLS LAST"
    elif sort_by == "hotness":
        order_clause = "le.hotness DESC NULLS LAST"
    elif sort_by == "liquidity":
        order_clause = "le.liquidity_score DESC NULLS LAST"
    elif sort_by == "time":
        order_clause = "le.event_time DESC"
    else:
        order_clause = "le.event_time DESC"

    # Query для получения сделок с аналитикой
    # Вычисляем profit_pct = ((floor_2nd - price) / price) * 100
    # hotness = liquidity_score + sales_7d/10
    query = f"""
        WITH latest_events AS (
            SELECT DISTINCT ON (me.gift_id)
                me.event_time,
                me.event_type,
                me.gift_id,
                me.gift_name,
                me.model,
                me.backdrop,
                me.pattern,
                me.number,
                me.price,
                me.source,
                COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg') as asset_key,
                CASE
                    WHEN aa.floor_2nd IS NOT NULL AND me.price > 0
                    THEN ((aa.floor_2nd - me.price) / me.price) * 100
                    ELSE NULL
                END as profit_pct,
                aa.floor_2nd as reference_price,
                'floor_2nd' as reference_type,
                aa.confidence_level,
                aa.liquidity_score,
                COALESCE(aa.liquidity_score, 0) + (COALESCE(aa.sales_7d, 0) / 10.0) as hotness,
                aa.sales_7d as sales_48h
            FROM market_events me
            LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
            WHERE {where_clause}
            ORDER BY me.gift_id, me.event_time DESC
        )
        SELECT *
        FROM latest_events le
        {f'WHERE COALESCE(le.profit_pct, 0) >= {min_profit}' if min_profit is not None and min_profit > 0 else ''}
        ORDER BY {order_clause}
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """

    params.extend([page_size, page * page_size])

    try:
        result = await db.pool.fetch(query, *params)

        # Преобразовать в DealCard
        deals = []
        for row in result:
            backdrop = row['backdrop']
            is_black_pack = backdrop in BLACK_PACK_BACKGROUNDS

            # Вычислить badge
            quality_badge = _compute_quality_badge(
                profit_pct=float(row['profit_pct'] or 0),
                liquidity_score=float(row['liquidity_score'] or 0),
                confidence_level=row['confidence_level'] or 'low',
                hotness=float(row['hotness'] or 0),
                is_black_pack=is_black_pack,
            )

            # Priority?
            is_priority = (float(row['hotness'] or 0) >= 7) or (float(row['profit_pct'] or 0) >= 25)

            # Фильтр priority
            if priority_only and not is_priority:
                continue

            deal = DealCard(
                asset_key=row['asset_key'],
                gift_id=row['gift_id'],
                gift_name=row['gift_name'] or 'Unknown',
                model=row['model'],
                backdrop=backdrop,
                pattern=row['pattern'],
                number=row['number'],
                photo_url=None,  # TODO: add to DB schema
                price=Decimal(str(row['price'])),
                reference_price=Decimal(str(row['reference_price'] or 0)),
                reference_type=row['reference_type'] or 'unknown',
                profit_pct=Decimal(str(row['profit_pct'] or 0)),
                confidence_level=ConfidenceLevel(row['confidence_level'] or 'low'),
                liquidity_score=Decimal(str(row['liquidity_score'] or 0)),
                hotness=Decimal(str(row['hotness'] or 0)),
                sales_48h=row['sales_48h'] or 0,
                event_type=EventType(row['event_type']),
                event_time=row['event_time'],
                source=EventSource(row['source']),
                is_black_pack=is_black_pack,
                is_priority=is_priority,
                quality_badge=quality_badge,
            )
            deals.append(deal)

        # Получить общее количество
        count_query = f"""
            WITH latest_events AS (
                SELECT DISTINCT ON (me.gift_id)
                    me.gift_id,
                    CASE
                        WHEN aa.floor_2nd IS NOT NULL AND me.price > 0
                        THEN ((aa.floor_2nd - me.price) / me.price) * 100
                        ELSE NULL
                    END as profit_pct
                FROM market_events me
                LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
                WHERE {where_clause}
                ORDER BY me.gift_id, me.event_time DESC
            )
            SELECT COUNT(*)
            FROM latest_events le
            {f'WHERE COALESCE(le.profit_pct, 0) >= {min_profit}' if min_profit is not None and min_profit > 0 else ''}
        """
        total = await db.pool.fetchval(count_query, *params[:len(params) - 2])

        return DealsFeedResponse(
            deals=deals,
            total=total or 0,
            page=page,
            page_size=page_size,
            has_more=(page + 1) * page_size < (total or 0),
        )

    except Exception as e:
        logger.error(f"Ошибка загрузки дилов: {e}", exc_info=True)
        # Fallback to empty
        return DealsFeedResponse(
            deals=[],
            total=0,
            page=page,
            page_size=page_size,
            has_more=False,
        )


@router.get("/overview", response_model=MarketOverview)
async def get_market_overview(
    db: DatabasePool = Depends(get_db_pool),
) -> MarketOverview:
    """Получить обзор рынка из БД."""

    time_threshold = datetime.now(timezone.utc) - timedelta(hours=2)

    try:
        # Активные дилы
        active_deals = await db.pool.fetchval(
            """
            SELECT COUNT(DISTINCT gift_id)
            FROM market_events
            WHERE event_time >= $1
                AND event_type IN ('listing', 'change_price')
            """,
            time_threshold,
        )

        # Горячие дилы (hotness >= 7)
        # hotness = liquidity_score + sales_7d/10
        hot_deals = await db.pool.fetchval(
            """
            SELECT COUNT(DISTINCT me.gift_id)
            FROM market_events me
            LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
            WHERE me.event_time >= $1
                AND me.event_type IN ('listing', 'change_price')
                AND (COALESCE(aa.liquidity_score, 0) + (COALESCE(aa.sales_7d, 0) / 10.0)) >= 7
            """,
            time_threshold,
        )

        # Приоритетные (hotness >= 7 OR profit >= 25)
        # profit_pct = ((floor_2nd - price) / price) * 100
        priority_deals = await db.pool.fetchval(
            """
            SELECT COUNT(DISTINCT me.gift_id)
            FROM market_events me
            LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
            WHERE me.event_time >= $1
                AND me.event_type IN ('listing', 'change_price')
                AND (
                    (COALESCE(aa.liquidity_score, 0) + (COALESCE(aa.sales_7d, 0) / 10.0)) >= 7
                    OR (aa.floor_2nd IS NOT NULL AND me.price > 0 AND ((aa.floor_2nd - me.price) / me.price) * 100 >= 25)
                )
            """,
            time_threshold,
        )

        # Black Pack floor (2nd lowest)
        black_pack_floor = await db.pool.fetchval(
            """
            SELECT price
            FROM active_listings
            WHERE backdrop = ANY($1)
            ORDER BY price ASC
            LIMIT 1 OFFSET 1
            """,
            list(BLACK_PACK_BACKGROUNDS),
        )

        # General floor (2nd lowest, не black pack)
        general_floor = await db.pool.fetchval(
            """
            SELECT price
            FROM active_listings
            WHERE backdrop != ALL($1)
            ORDER BY price ASC
            LIMIT 1 OFFSET 1
            """,
            list(BLACK_PACK_BACKGROUNDS),
        )

        # Trend: сравнить среднюю цену за последний час vs предыдущий час
        trend = Trend.STABLE
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)

        trend_row = await db.pool.fetchrow(
            """
            SELECT
                AVG(CASE WHEN event_time >= $1 THEN price END) as recent_avg,
                AVG(CASE WHEN event_time < $1 AND event_time >= $2 THEN price END) as prev_avg
            FROM market_events
            WHERE event_type = 'buy'
                AND event_time >= $2
            """,
            hour_ago,
            two_hours_ago,
        )

        if trend_row and trend_row['recent_avg'] and trend_row['prev_avg']:
            recent_avg = float(trend_row['recent_avg'])
            prev_avg = float(trend_row['prev_avg'])
            change_pct = ((recent_avg - prev_avg) / prev_avg) * 100

            if change_pct > 5:
                trend = Trend.RISING
            elif change_pct < -5:
                trend = Trend.FALLING

        return MarketOverview(
            active_deals=active_deals or 0,
            hot_deals=hot_deals or 0,
            priority_deals=priority_deals or 0,
            black_pack_floor=Decimal(str(black_pack_floor)) if black_pack_floor else None,
            general_floor=Decimal(str(general_floor)) if general_floor else None,
            market_trend=trend,
            last_updated=datetime.now(timezone.utc),
        )

    except Exception as e:
        logger.error(f"Ошибка загрузки обзора: {e}", exc_info=True)
        # Fallback
        return MarketOverview(
            active_deals=0,
            hot_deals=0,
            priority_deals=0,
            market_trend=Trend.STABLE,
            last_updated=datetime.now(timezone.utc),
        )
