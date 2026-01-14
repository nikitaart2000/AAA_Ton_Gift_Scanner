"""Test script for collectors."""

import asyncio
import logging
from src.services.scanner_service import ScannerService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main():
    """Run collector test."""
    logger.info("🚀 Starting AAA TON Gifts Scanner - Collector Test")
    logger.info("=" * 80)

    scanner = ScannerService()

    try:
        await scanner.start()
        logger.info("✅ Scanner started successfully!")
        logger.info("Listening for events... Press Ctrl+C to stop")
        logger.info("=" * 80)

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
