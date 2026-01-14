"""Test script for analytics engine."""

import asyncio
import logging
from src.storage.postgres import db
from src.storage.redis_client import redis_client
from src.core.analytics import analytics_engine
from sqlalchemy import text

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """Test analytics engine."""
    logger.info("🧠 Testing Analytics Engine")
    logger.info("=" * 80)

    # Connect to databases
    await db.connect()
    await redis_client.connect()

    try:
        # Get some active assets from DB
        async for session in db.get_session():
            query = text("""
            SELECT DISTINCT model, backdrop
            FROM market_events
            WHERE model IS NOT NULL
            LIMIT 5
            """)

            result = await session.execute(query)
            assets = result.fetchall()

        logger.info(f"Found {len(assets)} assets to analyze")
        logger.info("=" * 80)

        for model, backdrop in assets:
            backdrop_key = backdrop if backdrop else "no_bg"
            asset_key = f"{model}:{backdrop_key}"

            logger.info(f"\n📊 Analyzing: {asset_key}")
            logger.info("-" * 80)

            # Calculate analytics
            analytics = await analytics_engine.calculate_analytics(asset_key)

            if analytics:
                logger.info(f"✅ Analytics calculated:")
                logger.info(f"   Floors: 1st={analytics.floor_1st}, 2nd={analytics.floor_2nd}, 3rd={analytics.floor_3rd}")
                logger.info(f"   Listings: {analytics.listings_count}")
                logger.info(f"   Sales: 7d={analytics.sales_7d}, 30d={analytics.sales_30d}")
                logger.info(f"   Quantiles: Q25={analytics.price_q25}, Q50={analytics.price_q50}, Q75={analytics.price_q75}")
                logger.info(f"   Liquidity: {analytics.liquidity_score}/10")
                logger.info(f"   Confidence: {analytics.confidence_level.value if analytics.confidence_level else 'N/A'}")
                logger.info(f"   Trend: {analytics.trend.value if analytics.trend else 'N/A'}")

                # Calculate ARP
                arp = await analytics_engine.calculate_arp(analytics)
                logger.info(f"   ARP (Adaptive Reference Price): {arp} TON")

                # Calculate hotness
                hotness = await analytics_engine.calculate_hotness(asset_key, analytics)
                logger.info(f"   Hotness: {hotness}/10 🔥")
            else:
                logger.warning(f"❌ Failed to calculate analytics")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Analytics test completed!")

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
    finally:
        await redis_client.disconnect()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
