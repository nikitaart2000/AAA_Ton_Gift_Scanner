"""Swift Gifts event collector via POST API."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Awaitable, List
import aiohttp
from src.config import settings
from src.core.models import MarketEvent, EventType, EventSource, Marketplace

logger = logging.getLogger(__name__)

# Supported marketplaces via Swift Gifts API
SUPPORTED_SERVICES = ["portals", "mrkt"]


class SwiftGiftsCollector:
    """Collector for Swift Gifts market events using POST API."""

    def __init__(self):
        self.api_key = settings.SWIFT_GIFTS_API_KEY
        self.base_url = settings.SWIFT_GIFTS_BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.event_handler: Optional[Callable[[MarketEvent], Awaitable[None]]] = None
        # Track events per service + event_type combo
        self.last_event_ids: dict[str, set] = {}
        self.max_event_cache = 1000  # Keep track of last N event IDs per combo
        self.api_was_down: dict[str, bool] = {}  # Track API down state per service+type

    async def start(self, event_handler: Callable[[MarketEvent], Awaitable[None]]):
        """Start collecting events."""
        self.event_handler = event_handler
        self.running = True

        self.session = aiohttp.ClientSession(
            headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"}
        )

        logger.info(f"Swift Gifts collector started (services: {SUPPORTED_SERVICES})")

        # Start polling for all services and event types
        tasks = []
        for service in SUPPORTED_SERVICES:
            for event_type in ["buy", "listing", "change_price"]:
                tasks.append(self._poll_events(service, event_type))

        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop collecting events."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("Swift Gifts collector stopped")

    async def _poll_events(self, service: str, event_type: str):
        """Poll for events of a specific type from a specific service."""
        endpoint = f"{self.base_url}/api/actions/services/{service}"
        # Poll interval: 2 services × 3 types = 6 pollers, ~0.5s each = 3 RPS total
        poll_interval = 2
        cache_key = f"{service}:{event_type}"

        # Initialize tracking dicts for this service+type combo
        if cache_key not in self.last_event_ids:
            self.last_event_ids[cache_key] = set()
        if cache_key not in self.api_was_down:
            self.api_was_down[cache_key] = False

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
                        if self.api_was_down.get(cache_key, False):
                            logger.info(f"Swift Gifts API RECOVERED for {service}/{event_type}!")
                            self.api_was_down[cache_key] = False

                        await self._process_response(data, event_type, service)
                    else:
                        error_text = await response.text()

                        # Mark API as down and log with enhanced visibility
                        if not self.api_was_down.get(cache_key, False):
                            logger.error(
                                f"Swift Gifts API DOWN for {service}/{event_type}: {response.status} - "
                                f"Will retry every {poll_interval}s"
                            )
                            self.api_was_down[cache_key] = True
                        else:
                            # Less verbose logging for continuing failures
                            logger.debug(
                                f"Swift Gifts API still down for {service}/{event_type}: {response.status}"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Mark API as down on exception
                if not self.api_was_down.get(cache_key, False):
                    logger.error(f"Swift Gifts API ERROR for {service}/{event_type}: {e} - Will retry")
                    self.api_was_down[cache_key] = True
                else:
                    logger.debug(f"Error polling {service}/{event_type} events: {e}")

            await asyncio.sleep(poll_interval)

    async def _process_response(self, data: dict | list, event_type: str, service: str):
        """Process API response and extract events."""
        events_with_marketplace = []
        cache_key = f"{service}:{event_type}"

        # Initialize cache if not exists (for direct calls without _poll_events)
        if cache_key not in self.last_event_ids:
            self.last_event_ids[cache_key] = set()

        # Extract events from markets structure, preserving marketplace info
        if isinstance(data, dict) and "markets" in data:
            for market in data.get("markets", []):
                provider = market.get("provider", service)
                market_data = market.get("data", [])
                for item in market_data:
                    events_with_marketplace.append((item, provider))
        elif isinstance(data, list):
            for item in data:
                events_with_marketplace.append((item, service))
        elif isinstance(data, dict):
            # Check for common response structures
            if "events" in data:
                for item in data["events"]:
                    events_with_marketplace.append((item, service))
            elif "data" in data:
                for item in data["data"]:
                    events_with_marketplace.append((item, service))
            else:
                # Treat the dict itself as a single event
                events_with_marketplace.append((data, service))

        for event_data, marketplace_name in events_with_marketplace:
            try:
                # Generate unique event ID (include marketplace to avoid dupes across markets)
                event_id = self._generate_event_id(event_data, event_type, marketplace_name)

                # Skip if we've already processed this event
                if event_id in self.last_event_ids[cache_key]:
                    continue

                # Parse event with marketplace info
                event = self._parse_event(event_data, event_type, marketplace_name)
                if event:
                    # Track event ID
                    self.last_event_ids[cache_key].add(event_id)

                    # Limit cache size
                    if len(self.last_event_ids[cache_key]) > self.max_event_cache:
                        # Remove oldest half
                        old_ids = list(self.last_event_ids[cache_key])[: self.max_event_cache // 2]
                        for old_id in old_ids:
                            self.last_event_ids[cache_key].discard(old_id)

                    # Send to handler
                    if self.event_handler:
                        await self.event_handler(event)

            except Exception as e:
                logger.error(f"Error processing event: {e}", exc_info=True)

    def _generate_event_id(self, event_data: dict, event_type: str, marketplace: str = "") -> str:
        """Generate unique event ID."""
        # Use marketplace + slug + timestamp + price as unique identifier
        slug = event_data.get("slug") or ""
        timestamp = event_data.get("date") or ""
        price = event_data.get("price_ton") or ""

        return f"{marketplace}:{event_type}:{slug}:{timestamp}:{price}"

    def _parse_event(self, event_data: dict, event_type: str, marketplace_name: str = "") -> Optional[MarketEvent]:
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

            # Map marketplace name to enum
            marketplace = None
            if marketplace_name:
                try:
                    marketplace = Marketplace(marketplace_name.lower())
                except ValueError:
                    marketplace = Marketplace.UNKNOWN

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
                marketplace=marketplace,
                raw_data=event_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse event: {e}, data: {event_data}", exc_info=True)
            return None
