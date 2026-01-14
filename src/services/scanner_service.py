"""Main scanner service that coordinates collectors and data storage."""

import asyncio
import logging
from typing import List, Callable, Awaitable, Optional
from src.collectors.swift_gifts import SwiftGiftsCollector
# from src.collectors.tonnel_playwright import TonnelPlaywrightCollector  # DISABLED
from src.storage.postgres import db
from src.storage.redis_client import redis_client
from src.core.models import MarketEvent, ActiveListing, EventType, Alert
from src.core.alert_engine import alert_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ScannerService:
    """Main scanner service."""

    def __init__(self, alert_callback: Optional[Callable[[Alert], Awaitable[None]]] = None):
        self.swift_collector = SwiftGiftsCollector()
        # self.tonnel_collector = TonnelPlaywrightCollector()  # DISABLED: Cloudflare blocking all requests
        self.running = False
        self.alert_callback = alert_callback  # Callback to send alerts to bot

    async def start(self):
        """Start the scanner service."""
        logger.info("Starting scanner service...")

        # Connect to databases
        await db.connect()
        await redis_client.connect()

        self.running = True

        # Start collectors
        logger.info("Starting Swift Gifts collector only (Tonnel disabled due to Cloudflare)")
        await self.swift_collector.start(self.handle_market_event)
        # NOTE: Tonnel collector disabled - Cloudflare bypass unsuccessful

    async def stop(self):
        """Stop the scanner service."""
        logger.info("Stopping scanner service...")
        self.running = False

        await self.swift_collector.stop()
        # await self.tonnel_collector.stop()  # DISABLED

        await redis_client.disconnect()
        await db.disconnect()

    async def handle_market_event(self, event: MarketEvent):
        """Handle a market event from Swift Gifts."""
        try:
            logger.info(
                f"Event: {event.event_type.value} | {event.model} | "
                f"{event.backdrop or 'no_bg'} | {event.price} TON"
            )

            # Save to database
            async for session in db.get_session():
                # Save event
                query = text("""
                INSERT INTO market_events
                (event_time, event_type, gift_id, gift_name, model, backdrop, pattern, number,
                 price, price_old, source, raw_data)
                VALUES (:event_time, :event_type, :gift_id, :gift_name, :model, :backdrop,
                        :pattern, :number, :price, :price_old, :source, :raw_data)
                RETURNING id
                """)

                result = await session.execute(
                    query,
                    {
                        "event_time": event.event_time,
                        "event_type": event.event_type.value,
                        "gift_id": event.gift_id,
                        "gift_name": event.gift_name,
                        "model": event.model,
                        "backdrop": event.backdrop,
                        "pattern": event.pattern,
                        "number": event.number,
                        "price": float(event.price),
                        "price_old": float(event.price_old) if event.price_old else None,
                        "source": event.source.value,
                        "raw_data": None,
                    },
                )

                await session.commit()
                event_id = result.scalar()

                logger.debug(f"Saved event {event_id}")

                # Update active listings based on event type
                if event.event_type == EventType.LISTING:
                    # Add/update listing
                    listing_query = text("""
                    INSERT INTO active_listings
                    (gift_id, gift_name, model, backdrop, pattern, number, price,
                     listed_at, source, raw_data, last_updated)
                    VALUES (:gift_id, :gift_name, :model, :backdrop, :pattern, :number, :price,
                            :listed_at, :source, :raw_data, NOW())
                    ON CONFLICT (gift_id)
                    DO UPDATE SET
                        price = EXCLUDED.price,
                        last_updated = NOW()
                    """)

                    await session.execute(
                        listing_query,
                        {
                            "gift_id": event.gift_id,
                            "gift_name": event.gift_name,
                            "model": event.model,
                            "backdrop": event.backdrop,
                            "pattern": event.pattern,
                            "number": event.number,
                            "price": float(event.price),
                            "listed_at": event.event_time,
                            "source": event.source.value,
                            "raw_data": None,
                        },
                    )
                    await session.commit()

                elif event.event_type == EventType.BUY:
                    # Remove listing (sold)
                    remove_query = text("DELETE FROM active_listings WHERE gift_id = :gift_id")
                    await session.execute(remove_query, {"gift_id": event.gift_id})
                    await session.commit()

                elif event.event_type == EventType.CHANGE_PRICE:
                    # Update listing price
                    update_query = text("""
                    UPDATE active_listings
                    SET price = :price, last_updated = NOW()
                    WHERE gift_id = :gift_id
                    """)
                    await session.execute(
                        update_query, {"gift_id": event.gift_id, "price": float(event.price)}
                    )
                    await session.commit()

                # Invalidate cache for this asset
                await redis_client.delete(f"analytics:{event.asset_key}")
                await redis_client.delete(f"floor:{event.model}:{event.backdrop or 'no_bg'}:*")

            # Evaluate for alerts (only for listing and change_price events)
            if event.event_type in [EventType.LISTING, EventType.CHANGE_PRICE]:
                await self._evaluate_alert(event)

        except Exception as e:
            logger.error(f"Error handling event: {e}", exc_info=True)

    async def _evaluate_alert(self, event: MarketEvent):
        """Evaluate event for alert generation."""
        try:
            # Get active users (for now, just use dummy settings)
            # TODO: Get real user settings from DB
            from src.core.models import UserSettings, AlertMode, BackgroundFilter

            # User settings - более строгие для качественных сигналов
            test_settings = UserSettings(
                user_id=975050021,  # Real user ID
                mode=AlertMode.SPAM,
                profit_min=20,  # Требуем минимум 20% profit для LOW confidence
                background_filter=BackgroundFilter.ANY,
            )

            alert = await alert_engine.evaluate_event(event, test_settings)

            if alert and self.alert_callback:
                # Send alert to bot
                await self.alert_callback(alert)

        except Exception as e:
            logger.error(f"Error evaluating alert: {e}", exc_info=True)

    async def handle_listings(self, listings: List[ActiveListing]):
        """Handle batch of listings from Tonnel."""
        try:
            logger.info(f"Received {len(listings)} listings from Tonnel")

            async for session in db.get_session():
                # Upsert all listings
                for listing in listings:
                    query = text("""
                    INSERT INTO active_listings
                    (gift_id, gift_name, model, backdrop, pattern, number, price,
                     listed_at, export_at, source, raw_data, last_updated)
                    VALUES (:gift_id, :gift_name, :model, :backdrop, :pattern, :number, :price,
                            :listed_at, :export_at, :source, :raw_data, NOW())
                    ON CONFLICT (gift_id)
                    DO UPDATE SET
                        price = EXCLUDED.price,
                        gift_name = EXCLUDED.gift_name,
                        model = EXCLUDED.model,
                        backdrop = EXCLUDED.backdrop,
                        pattern = EXCLUDED.pattern,
                        number = EXCLUDED.number,
                        export_at = EXCLUDED.export_at,
                        last_updated = NOW()
                    """)

                    await session.execute(
                        query,
                        {
                            "gift_id": listing.gift_id,
                            "gift_name": listing.gift_name,
                            "model": listing.model,
                            "backdrop": listing.backdrop,
                            "pattern": listing.pattern,
                            "number": listing.number,
                            "price": float(listing.price),
                            "listed_at": listing.listed_at,
                            "export_at": listing.export_at,
                            "source": listing.source.value,
                            "raw_data": None,
                        },
                    )

                await session.commit()
                logger.info(f"Synced {len(listings)} listings to database")

        except Exception as e:
            logger.error(f"Error handling listings: {e}", exc_info=True)
