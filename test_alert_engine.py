"""Test script for alert engine with live events."""

import asyncio
import logging
from src.services.scanner_service import ScannerService
from src.core.models import Alert

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def handle_alert(alert: Alert):
    """Handle generated alert."""
    logger.info("=" * 80)
    logger.info("🚨 ALERT GENERATED!")
    logger.info("-" * 80)
    logger.info(f"Asset: {alert.model} | {alert.backdrop or 'no_bg'}")
    logger.info(f"Gift: {alert.gift_name} #{alert.number}")
    logger.info(f"Price: {alert.price} TON")
    logger.info(f"")
    logger.info(f"📊 OPPORTUNITY")
    logger.info(f"├─ Profit: +{alert.profit_pct}% vs {alert.reference_type}")
    logger.info(f"├─ Reference: {alert.reference_price} TON")
    logger.info(f"└─ Confidence: {alert.confidence_level.value.upper()}")
    logger.info(f"")
    logger.info(f"📈 MARKET CONTEXT")
    if alert.floor_black_pack:
        logger.info(f"├─ Black Pack 2nd Floor: {alert.floor_black_pack} TON")
    if alert.floor_general:
        logger.info(f"├─ General 2nd Floor: {alert.floor_general} TON")
    logger.info(f"└─ Liquidity: {alert.liquidity_score}/10")
    logger.info(f"")
    logger.info(f"💸 SALES")
    if alert.sales_q25 and alert.sales_q75:
        logger.info(
            f"├─ Q25: {alert.sales_q25} | Q75: {alert.sales_q75} | Max: {alert.sales_max}"
        )
    logger.info(f"└─ Sales 48h: {alert.sales_48h}")
    logger.info(f"")
    logger.info(f"🔥 Hotness: {alert.hotness}/10")
    logger.info(f"⭐ Priority: {'YES' if alert.is_priority else 'NO'}")
    logger.info(f"⏱️  Event: {alert.event_type.value}")
    logger.info("=" * 80)


async def main():
    """Run alert engine test with live data."""
    logger.info("🚨 Testing Alert Engine with Live Events")
    logger.info("=" * 80)
    logger.info("Connecting to collectors...")
    logger.info("Listening for events that trigger alerts...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 80)

    scanner = ScannerService(alert_callback=handle_alert)

    try:
        await scanner.start()

        # Run indefinitely
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Stopping scanner...")
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
    finally:
        await scanner.stop()
        logger.info("✅ Scanner stopped")


if __name__ == "__main__":
    asyncio.run(main())
