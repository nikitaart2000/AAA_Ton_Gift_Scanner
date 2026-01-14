"""Repository for market events."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from src.core.models import MarketEvent, EventType

logger = logging.getLogger(__name__)


class EventsRepository:
    """Repository for market_events table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_event(self, event: MarketEvent) -> int:
        """Save market event to database."""
        query = """
        INSERT INTO market_events
        (event_time, event_type, gift_id, gift_name, model, backdrop, pattern, number,
         price, price_old, source, raw_data)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id
        """

        result = await self.session.execute(
            query,
            (
                event.event_time,
                event.event_type.value,
                event.gift_id,
                event.gift_name,
                event.model,
                event.backdrop,
                event.pattern,
                event.number,
                float(event.price),
                float(event.price_old) if event.price_old else None,
                event.source.value,
                event.raw_data,
            ),
        )

        await self.session.commit()
        event_id = result.scalar()
        logger.debug(f"Saved event {event_id}: {event.event_type} for {event.gift_id}")
        return event_id

    async def get_recent_events(
        self,
        asset_key: str,
        hours: int = 24,
        event_types: Optional[List[EventType]] = None,
    ) -> List[dict]:
        """Get recent events for an asset."""
        since = datetime.utcnow() - timedelta(hours=hours)

        query = """
        SELECT event_time, event_type, price, price_old
        FROM market_events
        WHERE event_time >= $1
        """

        params = [since]

        # Parse asset_key to extract model and backdrop
        parts = asset_key.split(":")
        model = parts[0] if parts else None
        backdrop = parts[1] if len(parts) > 1 and parts[1] != "no_bg" else None

        if model:
            query += " AND model = $2"
            params.append(model)

        if backdrop:
            query += " AND backdrop = $3"
            params.append(backdrop)
        elif len(parts) > 1 and parts[1] == "no_bg":
            query += " AND backdrop IS NULL"

        if event_types:
            placeholders = ", ".join([f"${i+len(params)+1}" for i in range(len(event_types))])
            query += f" AND event_type IN ({placeholders})"
            params.extend([et.value for et in event_types])

        query += " ORDER BY event_time DESC LIMIT 100"

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "event_time": row[0],
                "event_type": row[1],
                "price": Decimal(str(row[2])),
                "price_old": Decimal(str(row[3])) if row[3] else None,
            }
            for row in rows
        ]

    async def get_sales(
        self, asset_key: str, days: int = 7
    ) -> List[dict]:
        """Get buy events (sales) for an asset."""
        since = datetime.utcnow() - timedelta(days=days)

        # Parse asset_key
        parts = asset_key.split(":")
        model = parts[0] if parts else None
        backdrop = parts[1] if len(parts) > 1 and parts[1] != "no_bg" else None

        query = """
        SELECT event_time, price
        FROM market_events
        WHERE event_type = 'buy' AND event_time >= $1
        """

        params = [since]

        if model:
            query += " AND model = $2"
            params.append(model)

        if backdrop:
            query += " AND backdrop = $3"
            params.append(backdrop)
        elif len(parts) > 1 and parts[1] == "no_bg":
            query += " AND backdrop IS NULL"

        query += " ORDER BY event_time DESC"

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "event_time": row[0],
                "price": Decimal(str(row[1])),
            }
            for row in rows
        ]

    async def count_sales(self, asset_key: str, days: int = 7) -> int:
        """Count sales for an asset."""
        sales = await self.get_sales(asset_key, days)
        return len(sales)

    async def get_last_sale_time(self, asset_key: str) -> Optional[datetime]:
        """Get timestamp of last sale."""
        sales = await self.get_sales(asset_key, days=30)
        if sales:
            return sales[0]["event_time"]
        return None
