"""Main entry point - AAA TON Gifts Scanner."""

import asyncio
import logging
from src.services.scanner_service import ScannerService
from src.bot.main import telegram_bot

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """Run the complete scanner system."""
    logger.info("=" * 80)
    logger.info("🎯 AAA TON GIFTS SCANNER")
    logger.info("=" * 80)
    logger.info("Starting all services...")
    logger.info("")

    # Create scanner with alert callback to bot
    scanner = ScannerService(alert_callback=telegram_bot.send_alert)

    try:
        # Start bot first
        await telegram_bot.start()
        logger.info("✅ Telegram bot ready")
        logger.info("")

        # Start scanner (collectors + alert engine)
        await scanner.start()
        logger.info("✅ Scanner ready")
        logger.info("")

        logger.info("=" * 80)
        logger.info("🚀 ALL SYSTEMS OPERATIONAL!")
        logger.info("=" * 80)
        logger.info("")
        logger.info("📊 Monitoring TON Gifts market in real-time...")
        logger.info("🔥 Alerts will be sent to Telegram when deals are found")
        logger.info("")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 80)

        # Run indefinitely
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("")
        logger.info("⚠️  Shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Stopping all services...")
        await scanner.stop()
        await telegram_bot.stop()
        logger.info("✅ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
