"""Swift Gifts event collector via POST API."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Awaitable, List
import aiohttp
from src.config import settings
from src.core.models import MarketEvent, EventType, EventSource

logger = logging.getLogger(__name__)


class SwiftGiftsCollector:
    """Collector for Swift Gifts market events using POST API."""

    def __init__(self):
        self.api_key = settings.SWIFT_GIFTS_API_KEY
        self.base_url = settings.SWIFT_GIFTS_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.event_handler: Optional[Callable[[MarketEvent], Awaitable[None]]] = None
        self.last_event_ids: dict[str, set] = {
            "buy": set(),
            "listing": set(),
            "change_price": set(),
        }
        self.max_event_cache = 1000  # Keep track of last N event IDs
        self.api_was_down: dict[str, bool] = {
            "buy": False,
            "listing": False,
            "change_price": False,
        }  # Track API down state per event type

    async def start(self, event_handler: Callable[[MarketEvent], Awaitable[None]]):
        """Start collecting events."""
        self.event_handler = event_handler
        self.running = True

        self.session = aiohttp.ClientSession(
            headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        )

        logger.info("Swift Gifts collector started")

        # Start polling for all event types
        await asyncio.gather(
            self._poll_events("buy"),
            self._poll_events("listing"),
            self._poll_events("change_price"),
        )

    async def stop(self):
        """Stop collecting events."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("Swift Gifts collector stopped")

    async def _poll_events(self, event_type: str):
        """Poll for events of a specific type."""
        endpoint = f"{self.base_url}/api/actions/services/portals"
        poll_interval = 2  # Poll every 2 seconds (3 types × 0.5 RPS = 1.5 RPS total)

        while self.running:
            try:
                # Request with type parameter
                payload = {"type": event_type}
                params = {"page": 0, "mode": "collection_number"}

                async with self.session.post(
                    endpoint, json=payload, params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Check if API was previously down and now recovered
                        if self.api_was_down.get(event_type, False):
                            logger.info(f"✅ Swift Gifts API RECOVERED for {event_type} events!")
                            self.api_was_down[event_type] = False

                        await self._process_response(data, event_type)
                    else:
                        error_text = await response.text()

                        # Mark API as down and log with enhanced visibility
                        if not self.api_was_down.get(event_type, False):
                            logger.error(
                                f"❌ Swift Gifts API DOWN for {event_type}: {response.status} - "
                                f"Will retry every {poll_interval}s"
                            )
                            self.api_was_down[event_type] = True
                        else:
                            # Less verbose logging for continuing failures
                            logger.debug(
                                f"Swift Gifts API still down for {event_type}: {response.status}"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Mark API as down on exception
                if not self.api_was_down.get(event_type, False):
                    logger.error(f"❌ Swift Gifts API ERROR for {event_type}: {e} - Will retry")
                    self.api_was_down[event_type] = True
                else:
                    logger.debug(f"Error polling {event_type} events: {e}")

            await asyncio.sleep(poll_interval)

    async def _process_response(self, data: dict | list, event_type: str):
        """Process API response and extract events."""
        events = []

        # Extract events from markets structure
        if isinstance(data, dict) and "markets" in data:
            for market in data.get("markets", []):
                market_data = market.get("data", [])
                events.extend(market_data)
        elif isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            # Check for common response structures
            if "events" in data:
                events = data["events"]
            elif "data" in data:
                events = data["data"]
            else:
                # Treat the dict itself as a single event
                events = [data]

        for event_data in events:
            try:
                # Generate unique event ID
                event_id = self._generate_event_id(event_data, event_type)

                # Skip if we've already processed this event
                if event_id in self.last_event_ids[event_type]:
                    continue

                # Parse event
                event = self._parse_event(event_data, event_type)
                if event:
                    # Track event ID
                    self.last_event_ids[event_type].add(event_id)

                    # Limit cache size
                    if len(self.last_event_ids[event_type]) > self.max_event_cache:
                        # Remove oldest half
                        old_ids = list(self.last_event_ids[event_type])[: self.max_event_cache // 2]
                        for old_id in old_ids:
                            self.last_event_ids[event_type].discard(old_id)

                    # Send to handler
                    if self.event_handler:
                        await self.event_handler(event)

            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)

    def _generate_event_id(self, event_data: dict, event_type: str) -> str:
        """Generate unique event ID."""
        # Use slug + timestamp + price as unique identifier
        slug = event_data.get("slug") or ""
        timestamp = event_data.get("date") or ""
        price = event_data.get("price_ton") or ""

        return f"{event_type}:{slug}:{timestamp}:{price}"

    def _parse_event(self, event_data: dict, event_type: str) -> Optional[MarketEvent]:
        """Parse event data into MarketEvent."""
        try:
            # Extract slug as gift_id
            gift_id = event_data.get("slug")
            if not gift_id:
                logger.warning(f"Event missing slug: {event_data}")
                return None

            # Parse timestamp
            timestamp_str = event_data.get("date")

            if timestamp_str:
                # Handle ISO format
                event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                event_time = datetime.utcnow()

            # Extract price
            price_value = event_data.get("price_ton")
            if price_value is None:
                logger.warning(f"Event missing price_ton: {event_data}")
                return None

            price = Decimal(str(price_value))

            # Extract old price for change_price events
            price_old = None
            if event_type == "change_price":
                price_old_value = event_data.get("price_old_ton")
                if price_old_value is not None:
                    price_old = Decimal(str(price_old_value))

            # Extract metadata
            gift_name = event_data.get("title")
            collection = event_data.get("collection")
            number = event_data.get("number")
            photo_url = event_data.get("photo_url")

            # Extract attributes
            attributes = event_data.get("attributes", {})
            model = attributes.get("model", {}).get("value") if "model" in attributes else None
            backdrop = (
                attributes.get("backdrop", {}).get("value") if "backdrop" in attributes else None
            )
            symbol = (
                attributes.get("symbol", {}).get("value") if "symbol" in attributes else None
            )

            return MarketEvent(
                event_time=event_time,
                event_type=EventType(event_type),
                gift_id=gift_id,
                gift_name=gift_name or collection,
                model=model,
                backdrop=backdrop,
                pattern=symbol,  # Use symbol as pattern
                number=number,
                price=price,
                price_old=price_old,
                photo_url=photo_url,
                source=EventSource.SWIFT_GIFTS,
                raw_data=event_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse event: {e}, data: {event_data}", exc_info=True)
            return None
