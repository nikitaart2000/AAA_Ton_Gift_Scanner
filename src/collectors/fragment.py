"""Fragment marketplace scraper for TON Gifts.

Scrapes gift collections, listings, and sales from fragment.com.
Uses curl_cffi to bypass Cloudflare protection.
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from curl_cffi.requests import AsyncSession
from src.core.models import MarketEvent, EventType, EventSource

logger = logging.getLogger(__name__)


class FragmentCollector:
    """Scraper for Fragment marketplace gift data."""

    BASE_URL = "https://fragment.com"

    def __init__(self):
        self.session: Optional[AsyncSession] = None

    def _random_user_agent(self) -> str:
        """Generate random user agent."""
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        return random.choice(agents)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "User-Agent": self._random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    async def fetch_gift_collections(self) -> List[Dict[str, Any]]:
        """
        Fetch list of all gift collections from Fragment.

        Returns list of dicts with collection info:
        - slug: collection URL slug
        - name: display name
        - total_items: number of items in collection
        """
        collections = []

        async with AsyncSession(impersonate="chrome120") as session:
            try:
                response = await session.get(
                    f"{self.BASE_URL}/gifts",
                    headers=self._get_headers(),
                    timeout=30,
                )

                if response.status_code == 200:
                    html = response.text

                    # Parse collection links from HTML
                    # Pattern: href="/gift/collection-slug"
                    pattern = r'href="/gift/([^"]+)"[^>]*>.*?<div[^>]*class="[^"]*gift-collection-name[^"]*"[^>]*>([^<]+)</div>'
                    matches = re.findall(pattern, html, re.DOTALL)

                    seen_slugs = set()
                    for slug, name in matches:
                        if slug not in seen_slugs:
                            seen_slugs.add(slug)
                            collections.append({
                                "slug": slug.strip(),
                                "name": name.strip(),
                            })

                    # Alternative pattern for simpler structure
                    if not collections:
                        pattern2 = r'href="/gift/([^"]+)"'
                        slugs = re.findall(pattern2, html)
                        for slug in set(slugs):
                            if slug and not slug.startswith("?"):
                                collections.append({"slug": slug, "name": slug.replace("-", " ").title()})

                    logger.info(f"Found {len(collections)} gift collections on Fragment")
                else:
                    logger.error(f"Failed to fetch collections: {response.status_code}")

            except Exception as e:
                logger.error(f"Error fetching collections: {e}", exc_info=True)

        return collections

    async def fetch_collection_listings(
        self,
        collection_slug: str,
        status: str = "sale",  # 'sale', 'sold', 'auction'
        page: int = 1,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch listings for a specific collection.

        Args:
            collection_slug: Collection URL slug
            status: 'sale' for active listings, 'sold' for past sales
            page: Page number
            limit: Items per page

        Returns list of listing dicts.
        """
        listings = []

        async with AsyncSession(impersonate="chrome120") as session:
            try:
                url = f"{self.BASE_URL}/gift/{collection_slug}"
                params = {"sort": "price_asc", "filter": status}

                response = await session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30,
                )

                if response.status_code == 200:
                    html = response.text

                    # Parse gift items from HTML
                    # This is a simplified pattern - real parsing depends on Fragment's HTML structure
                    item_pattern = r'data-gift-id="(\d+)"[^>]*>.*?price[^>]*>([0-9.,]+)\s*TON'
                    matches = re.findall(item_pattern, html, re.DOTALL | re.IGNORECASE)

                    for gift_id, price_str in matches:
                        try:
                            price = Decimal(price_str.replace(",", "").strip())
                            listings.append({
                                "gift_id": gift_id,
                                "collection": collection_slug,
                                "price": price,
                                "status": status,
                            })
                        except Exception:
                            continue

                    logger.info(f"Found {len(listings)} {status} listings for {collection_slug}")
                else:
                    logger.error(f"Failed to fetch {collection_slug} listings: {response.status_code}")

            except Exception as e:
                logger.error(f"Error fetching {collection_slug}: {e}", exc_info=True)

        return listings

    async def fetch_sold_gifts(
        self,
        collection_slug: str,
        max_pages: int = 10,
    ) -> List[MarketEvent]:
        """
        Fetch sold gifts (historical sales) for a collection.

        Args:
            collection_slug: Collection URL slug
            max_pages: Maximum pages to fetch

        Returns list of MarketEvent objects.
        """
        events = []

        async with AsyncSession(impersonate="chrome120") as session:
            for page in range(1, max_pages + 1):
                try:
                    url = f"{self.BASE_URL}/gift/{collection_slug}"
                    params = {"filter": "sold", "page": page}

                    response = await session.get(
                        url,
                        headers=self._get_headers(),
                        params=params,
                        timeout=30,
                    )

                    if response.status_code == 200:
                        html = response.text

                        # Parse sold items - simplified pattern
                        # Real implementation needs to match Fragment's actual HTML
                        item_pattern = r'data-gift-id="(\d+)".*?sold.*?([0-9.,]+)\s*TON.*?(\d{1,2}\s+\w+\s+\d{4}|\d+\s+hours?\s+ago)'
                        matches = re.findall(item_pattern, html, re.DOTALL | re.IGNORECASE)

                        if not matches:
                            logger.info(f"No more sold items at page {page}")
                            break

                        for gift_id, price_str, date_str in matches:
                            try:
                                price = Decimal(price_str.replace(",", "").strip())
                                event_time = self._parse_date(date_str)

                                event = MarketEvent(
                                    event_time=event_time or datetime.now(timezone.utc),
                                    event_type=EventType.BUY,
                                    gift_id=f"fragment-{gift_id}",
                                    gift_name=collection_slug.replace("-", " ").title(),
                                    price=price,
                                    source=EventSource.FRAGMENT,
                                    raw_data={"fragment_id": gift_id, "collection": collection_slug},
                                )
                                events.append(event)
                            except Exception as e:
                                logger.debug(f"Failed to parse sold item: {e}")

                        logger.info(f"Fetched {len(matches)} sold items from page {page}")

                    else:
                        logger.error(f"Failed to fetch sold page {page}: {response.status_code}")
                        break

                    # Rate limiting
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"Error fetching sold page {page}: {e}", exc_info=True)
                    break

        logger.info(f"Total sold items fetched for {collection_slug}: {len(events)}")
        return events

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse Fragment date string to datetime."""
        try:
            date_str = date_str.strip().lower()

            # Handle relative dates
            if "hour" in date_str:
                hours = int(re.search(r"(\d+)", date_str).group(1))
                return datetime.now(timezone.utc).replace(microsecond=0)

            if "day" in date_str:
                days = int(re.search(r"(\d+)", date_str).group(1))
                return datetime.now(timezone.utc).replace(microsecond=0)

            # Handle absolute dates (e.g., "14 Jan 2025")
            formats = [
                "%d %b %Y",
                "%d %B %Y",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")

        return None

    async def backfill_all_collections(
        self,
        event_handler=None,
        max_pages_per_collection: int = 5,
    ) -> int:
        """
        Backfill sales data from all Fragment collections.

        Args:
            event_handler: Async function to call for each event
            max_pages_per_collection: Max pages to fetch per collection

        Returns total events backfilled.
        """
        logger.info("🔄 Starting Fragment backfill...")

        collections = await self.fetch_gift_collections()

        if not collections:
            logger.warning("No collections found on Fragment")
            return 0

        total_events = 0

        for i, collection in enumerate(collections):
            slug = collection["slug"]
            logger.info(f"Processing collection {i+1}/{len(collections)}: {slug}")

            events = await self.fetch_sold_gifts(slug, max_pages=max_pages_per_collection)

            for event in events:
                if event_handler:
                    await event_handler(event)
                total_events += 1

            # Rate limiting between collections
            await asyncio.sleep(3)

        logger.info(f"✅ Fragment backfill complete! Total events: {total_events}")
        return total_events
