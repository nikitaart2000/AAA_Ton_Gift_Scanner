#!/usr/bin/env python3
"""
Backfill historical sales data from multiple sources.

Usage:
    python scripts/backfill.py --source tonnel --pages 50
    python scripts/backfill.py --source fragment
    python scripts/backfill.py --source all
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.collectors.tonnel import TonnelCollector
from src.collectors.fragment import FragmentCollector
from src.storage.postgres import db
from src.core.models import MarketEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class BackfillRunner:
    """Run backfill from multiple sources."""

    def __init__(self):
        self.stats = {
            "tonnel": {"total": 0, "new": 0, "duplicates": 0, "errors": 0},
            "fragment": {"total": 0, "new": 0, "duplicates": 0, "errors": 0},
        }

    async def save_event(self, event: MarketEvent, source: str) -> bool:
        """Save event to database, handle duplicates."""
        self.stats[source]["total"] += 1

        try:
            async for session in db.get_session():
                # Use INSERT with ON CONFLICT to handle duplicates gracefully
                query = text("""
                INSERT INTO market_events
                (event_time, event_type, gift_id, gift_name, model, backdrop, pattern, number,
                 price, price_old, source, raw_data)
                VALUES (:event_time, :event_type, :gift_id, :gift_name, :model, :backdrop,
                        :pattern, :number, :price, :price_old, :source, :raw_data)
                ON CONFLICT DO NOTHING
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

                if event_id:
                    self.stats[source]["new"] += 1
                    return True
                else:
                    self.stats[source]["duplicates"] += 1
                    return False

        except Exception as e:
            self.stats[source]["errors"] += 1
            logger.error(f"Error saving event: {e}")
            return False

        return False

    async def run_tonnel_backfill(self, max_pages: int = 50):
        """Run Tonnel backfill."""
        logger.info("=" * 60)
        logger.info("🔄 STARTING TONNEL BACKFILL")
        logger.info("=" * 60)

        collector = TonnelCollector()

        async def handler(event: MarketEvent):
            await self.save_event(event, "tonnel")

        total = await collector.backfill_sales(
            max_pages=max_pages,
            event_handler=handler,
        )

        logger.info(f"Tonnel backfill complete:")
        logger.info(f"  Total processed: {self.stats['tonnel']['total']}")
        logger.info(f"  New events: {self.stats['tonnel']['new']}")
        logger.info(f"  Duplicates skipped: {self.stats['tonnel']['duplicates']}")

        return total

    async def run_fragment_backfill(self, max_pages_per_collection: int = 5):
        """Run Fragment backfill."""
        logger.info("=" * 60)
        logger.info("🔄 STARTING FRAGMENT BACKFILL")
        logger.info("=" * 60)

        collector = FragmentCollector()

        async def handler(event: MarketEvent):
            await self.save_event(event, "fragment")

        total = await collector.backfill_all_collections(
            event_handler=handler,
            max_pages_per_collection=max_pages_per_collection,
        )

        logger.info(f"Fragment backfill complete:")
        logger.info(f"  Total processed: {self.stats['fragment']['total']}")
        logger.info(f"  New events: {self.stats['fragment']['new']}")
        logger.info(f"  Duplicates skipped: {self.stats['fragment']['duplicates']}")

        return total

    async def run_all(self, tonnel_pages: int = 50, fragment_pages: int = 5):
        """Run all backfills."""
        logger.info("🚀 STARTING FULL BACKFILL FROM ALL SOURCES")
        logger.info("")

        # Initialize database
        await db.init()

        try:
            # Tonnel first (usually has more data)
            await self.run_tonnel_backfill(max_pages=tonnel_pages)

            # Then Fragment
            await self.run_fragment_backfill(max_pages_per_collection=fragment_pages)

            # Summary
            logger.info("")
            logger.info("=" * 60)
            logger.info("📊 BACKFILL SUMMARY")
            logger.info("=" * 60)

            total_new = sum(s["new"] for s in self.stats.values())
            total_dups = sum(s["duplicates"] for s in self.stats.values())
            total_all = sum(s["total"] for s in self.stats.values())

            logger.info(f"Total events processed: {total_all}")
            logger.info(f"New events saved: {total_new}")
            logger.info(f"Duplicates skipped: {total_dups}")
            logger.info("")
            logger.info("Per-source breakdown:")
            for source, stats in self.stats.items():
                logger.info(f"  {source}: {stats['new']} new / {stats['total']} total")

        finally:
            await db.close()


async def main():
    parser = argparse.ArgumentParser(description="Backfill historical sales data")
    parser.add_argument(
        "--source",
        choices=["tonnel", "fragment", "all"],
        default="all",
        help="Data source to backfill from",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=50,
        help="Max pages to fetch (for Tonnel)",
    )
    parser.add_argument(
        "--fragment-pages",
        type=int,
        default=5,
        help="Max pages per collection (for Fragment)",
    )

    args = parser.parse_args()

    runner = BackfillRunner()

    # Initialize database
    await db.init()

    try:
        if args.source == "tonnel":
            await runner.run_tonnel_backfill(max_pages=args.pages)
        elif args.source == "fragment":
            await runner.run_fragment_backfill(max_pages_per_collection=args.fragment_pages)
        else:
            await runner.run_all(
                tonnel_pages=args.pages,
                fragment_pages=args.fragment_pages,
            )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
