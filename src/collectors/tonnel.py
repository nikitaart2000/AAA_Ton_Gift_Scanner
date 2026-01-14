"""Tonnel market collector via REST API."""

import asyncio
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Awaitable, List
from curl_cffi.requests import AsyncSession
from src.config import settings
from src.core.models import ActiveListing, EventSource

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
