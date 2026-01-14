"""Tonnel market collector via REST API.

Provides:
- Real-time listing sync
- Floor prices for all models (filterStats)
- Sale history backfill
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable, List, Dict, Any
from curl_cffi.requests import AsyncSession
from src.config import settings
from src.core.models import ActiveListing, MarketEvent, EventType, EventSource

logger = logging.getLogger(__name__)


class TonnelCollector:
    """Collector for Tonnel market listings."""

    def __init__(self):
        self.base_url = settings.TONNEL_BASE_URL
        self.auth_data = settings.TONNEL_AUTH_DATA
        self.session: Optional[AsyncSession] = None
        self.running = False
        self.listing_handler: Optional[Callable[[List[ActiveListing]], Awaitable[None]]] = None

    async def start(self, listing_handler: Callable[[List[ActiveListing]], Awaitable[None]]):
        """Start collecting listings."""
        self.listing_handler = listing_handler
        self.running = True

        logger.info("Tonnel collector started")

        # Start periodic sync
        await self._sync_listings_loop()

    async def stop(self):
        """Stop collector."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("Tonnel collector stopped")

    async def _sync_listings_loop(self):
        """Periodically sync all active listings."""
        while self.running:
            try:
                await self._fetch_and_process_listings()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error syncing listings: {e}", exc_info=True)

            # Wait before next sync
            await asyncio.sleep(settings.TONNEL_SYNC_INTERVAL)

    async def _fetch_and_process_listings(self):
        """Fetch all listings and process them."""
        logger.info("Fetching listings from Tonnel...")

        async with AsyncSession(impersonate="chrome110") as session:
            # Prepare headers
            headers = {
                "origin": "https://market.tonnel.network",
                "referer": "https://market.tonnel.network/",
                "user-agent": self._random_user_agent(),
                "content-type": "application/json",
            }

            # Prepare request body
            payload = {
                "authData": self.auth_data,
                "page": 1,
                "limit": 100,  # Fetch max per page
                "sort": "price_asc",
            }

            all_listings = []
            page = 1
            max_pages = 10  # Safety limit

            while page <= max_pages:
                payload["page"] = page

                try:
                    response = await session.post(
                        f"{self.base_url}/api/pageGifts",
                        headers=headers,
                        json=payload,
                        timeout=30,
                    )

                    if response.status_code == 200:
                        data = response.json()

                        # Extract listings
                        listings_data = data if isinstance(data, list) else data.get("gifts", [])

                        if not listings_data:
                            break  # No more listings

                        # Parse listings
                        for listing_data in listings_data:
                            listing = self._parse_listing(listing_data)
                            if listing:
                                all_listings.append(listing)

                        logger.info(f"Fetched {len(listings_data)} listings from page {page}")

                        # Check if there are more pages
                        if len(listings_data) < payload["limit"]:
                            break  # Last page

                        page += 1
                    else:
                        logger.error(f"Failed to fetch listings: {response.status_code}")
                        break

                except Exception as e:
                    logger.error(f"Error fetching page {page}: {e}", exc_info=True)
                    break

            logger.info(f"Total listings fetched: {len(all_listings)}")

            # Send to handler
            if all_listings and self.listing_handler:
                await self.listing_handler(all_listings)

    def _parse_listing(self, listing_data: dict) -> Optional[ActiveListing]:
        """Parse listing data into ActiveListing."""
        try:
            gift_id = listing_data.get("gift_id") or listing_data.get("asset")
            if not gift_id:
                return None

            price_value = listing_data.get("price")
            if price_value is None:
                return None

            price = Decimal(str(price_value))

            # Parse timestamps
            listed_at = None
            export_at = None

            if listing_data.get("listed_at"):
                listed_at = self._parse_timestamp(listing_data["listed_at"])

            if listing_data.get("export_at"):
                export_at = self._parse_timestamp(listing_data["export_at"])

            # Extract metadata
            gift_name = listing_data.get("gift_name")
            model = listing_data.get("model")
            backdrop = listing_data.get("backdrop")
            pattern = listing_data.get("pattern")
            number = listing_data.get("gift_num") or listing_data.get("number")

            return ActiveListing(
                gift_id=gift_id,
                gift_name=gift_name,
                model=model,
                backdrop=backdrop,
                pattern=pattern,
                number=number,
                price=price,
                listed_at=listed_at,
                export_at=export_at,
                source=EventSource.TONNEL,
                raw_data=listing_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse listing: {e}, data: {listing_data}", exc_info=True)
            return None

    def _parse_timestamp(self, ts) -> Optional[datetime]:
        """Parse timestamp to datetime."""
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts)
            elif isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception as e:
            logger.error(f"Failed to parse timestamp {ts}: {e}")
        return None

    def _random_user_agent(self) -> str:
        """Generate random user agent."""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        ]
        return random.choice(agents)

    async def fetch_sale_history(self, gift_id: str) -> List[dict]:
        """Fetch sale history for a specific gift."""
        async with AsyncSession(impersonate="chrome110") as session:
            headers = {
                "origin": "https://market.tonnel.network",
                "referer": "https://market.tonnel.network/",
                "user-agent": self._random_user_agent(),
                "content-type": "application/json",
            }

            payload = {
                "authData": self.auth_data,
                "gift_id": gift_id,
            }

            try:
                response = await session.post(
                    f"{self.base_url}/api/saleHistory",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, list) else data.get("sales", [])

            except Exception as e:
                logger.error(f"Error fetching sale history for {gift_id}: {e}", exc_info=True)

        return []

    async def fetch_gift_metadata(self, gift_id: str) -> Optional[dict]:
        """Fetch metadata for a specific gift."""
        async with AsyncSession(impersonate="chrome110") as session:
            headers = {
                "origin": "https://market.tonnel.network",
                "referer": "https://market.tonnel.network/",
                "user-agent": self._random_user_agent(),
                "content-type": "application/json",
            }

            payload = {"authData": self.auth_data}

            try:
                response = await session.post(
                    f"{self.base_url}/api/giftData/{gift_id}",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if response.status_code == 200:
                    return response.json()

            except Exception as e:
                logger.error(f"Error fetching metadata for {gift_id}: {e}", exc_info=True)

        return None

    async def fetch_floor_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch floor prices for ALL gift models.

        Returns dict like:
        {
            "Toy Bear": {
                "Wizard": {"floor_price": 10.5, "count": 25, "rarity": 2.5},
                "Knight": {"floor_price": 8.2, "count": 30, "rarity": 3.1},
                ...
            },
            ...
        }
        """
        async with AsyncSession(impersonate="chrome110") as session:
            headers = {
                "origin": "https://market.tonnel.network",
                "referer": "https://market.tonnel.network/",
                "user-agent": self._random_user_agent(),
                "content-type": "application/json",
            }

            payload = {"authData": self.auth_data}

            try:
                response = await session.post(
                    f"{self.base_url}/api/filterStatsPretty",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    # Response format: {"data": {"gift_name": {"model": {"floorPrice": X, "howMany": Y, "rarity": Z}}}}
                    result = {}
                    raw_data = data.get("data", data) if isinstance(data, dict) else {}

                    for gift_name, models in raw_data.items():
                        if isinstance(models, dict):
                            result[gift_name] = {}
                            for model_name, stats in models.items():
                                if isinstance(stats, dict):
                                    result[gift_name][model_name] = {
                                        "floor_price": Decimal(str(stats.get("floorPrice", 0))) if stats.get("floorPrice") else None,
                                        "count": stats.get("howMany", 0),
                                        "rarity": stats.get("rarity", 0),
                                    }

                    logger.info(f"✅ Fetched floor stats for {len(result)} gift collections")
                    return result
                else:
                    logger.error(f"Failed to fetch floor stats: {response.status_code}")

            except Exception as e:
                logger.error(f"Error fetching floor stats: {e}", exc_info=True)

        return {}

    async def fetch_global_sale_history(
        self,
        page: int = 1,
        limit: int = 100,
        sale_type: str = "ALL",
        gift_name: str = None,
        model: str = None,
        backdrop: str = None,
    ) -> List[MarketEvent]:
        """
        Fetch global sale history from Tonnel.

        Args:
            page: Page number (1-indexed)
            limit: Items per page (max 100)
            sale_type: ALL, SALE, INTERNAL_SALE, or BID
            gift_name: Filter by gift collection name
            model: Filter by model
            backdrop: Filter by backdrop

        Returns:
            List of MarketEvent objects representing sales (buy events)
        """
        async with AsyncSession(impersonate="chrome110") as session:
            headers = {
                "origin": "https://market.tonnel.network",
                "referer": "https://market.tonnel.network/",
                "user-agent": self._random_user_agent(),
                "content-type": "application/json",
            }

            payload = {
                "authData": self.auth_data,
                "page": page,
                "limit": limit,
                "type": sale_type,
                "sort": "latest",
            }

            # Add optional filters
            if gift_name:
                payload["gift_name"] = gift_name
            if model:
                payload["model"] = model
            if backdrop:
                payload["backdrop"] = backdrop

            try:
                response = await session.post(
                    f"{self.base_url}/api/saleHistory",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if response.status_code == 200:
                    data = response.json()
                    sales_data = data if isinstance(data, list) else data.get("sales", data.get("data", []))

                    events = []
                    for sale in sales_data:
                        event = self._parse_sale_to_event(sale)
                        if event:
                            events.append(event)

                    logger.info(f"Fetched {len(events)} sales from Tonnel (page {page})")
                    return events
                else:
                    logger.error(f"Failed to fetch sale history: {response.status_code}")

            except Exception as e:
                logger.error(f"Error fetching sale history: {e}", exc_info=True)

        return []

    def _parse_sale_to_event(self, sale_data: dict) -> Optional[MarketEvent]:
        """Parse Tonnel sale data into MarketEvent."""
        try:
            # Extract gift_id
            gift_id = sale_data.get("gift_id") or sale_data.get("asset") or sale_data.get("slug")
            if not gift_id:
                return None

            # Extract price
            price_value = sale_data.get("price") or sale_data.get("sale_price")
            if price_value is None:
                return None
            price = Decimal(str(price_value))

            # Parse timestamp
            event_time = None
            ts = sale_data.get("date") or sale_data.get("sold_at") or sale_data.get("timestamp")
            if ts:
                event_time = self._parse_timestamp(ts)
            if not event_time:
                event_time = datetime.now(timezone.utc)

            # Extract metadata
            gift_name = sale_data.get("gift_name") or sale_data.get("collection")
            model = sale_data.get("model")
            backdrop = sale_data.get("backdrop")
            pattern = sale_data.get("pattern") or sale_data.get("symbol")
            number = sale_data.get("gift_num") or sale_data.get("number")

            return MarketEvent(
                event_time=event_time,
                event_type=EventType.BUY,
                gift_id=str(gift_id),
                gift_name=gift_name,
                model=model,
                backdrop=backdrop,
                pattern=pattern,
                number=number,
                price=price,
                source=EventSource.TONNEL,
                raw_data=sale_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse sale to event: {e}, data: {sale_data}", exc_info=True)
            return None

    async def backfill_sales(
        self,
        max_pages: int = 50,
        event_handler: Optional[Callable[[MarketEvent], Awaitable[None]]] = None
    ) -> int:
        """
        Backfill historical sales from Tonnel.

        Args:
            max_pages: Maximum pages to fetch (100 items per page)
            event_handler: Optional handler for each event

        Returns:
            Total number of sales backfilled
        """
        logger.info(f"🔄 Starting Tonnel sales backfill (max {max_pages} pages)...")

        total_events = 0
        page = 1

        while page <= max_pages:
            events = await self.fetch_global_sale_history(page=page, limit=100)

            if not events:
                logger.info(f"No more sales at page {page}, stopping backfill")
                break

            # Process events
            for event in events:
                if event_handler:
                    await event_handler(event)
                total_events += 1

            logger.info(f"📊 Backfill progress: page {page}/{max_pages}, total events: {total_events}")

            # Rate limiting
            await asyncio.sleep(1)  # 1 RPS to be safe
            page += 1

        logger.info(f"✅ Tonnel backfill complete! Total sales: {total_events}")
        return total_events
