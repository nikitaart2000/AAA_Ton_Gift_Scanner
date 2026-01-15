"""MRKT marketplace API service for getting listing IDs."""

import logging
import time
import asyncio
import aiohttp
import urllib.parse
from typing import Optional

from telethon.tl.functions.messages import RequestWebViewRequest

from src.services.telegram_client import tg_client_manager

logger = logging.getLogger(__name__)


class MRKTApiService:
    """Service for querying MRKT marketplace API to get listing IDs."""

    def __init__(self):
        self.api_url = "https://api.tgmrkt.io/api/v1"
        self.webapp_url = "https://tgmrkt.io"

        # Auth token
        self._init_data: Optional[str] = None
        self._init_data_expires: float = 0

        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None

        # Cache listing IDs by slug
        self._cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = 60  # 1 minute (listings can change)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _refresh_init_data(self) -> bool:
        """Get fresh Web App init data from Telegram."""
        # Check if still valid (outside lock for performance)
        if self._init_data and time.time() < self._init_data_expires:
            return True

        # Use shared Telegram client with its lock
        async with tg_client_manager.lock:
            # Double-check after acquiring lock
            if self._init_data and time.time() < self._init_data_expires:
                return True

            client = await tg_client_manager.get_client()
            if not client:
                return False

            try:
                # Request Web View for MRKT
                result = await client(RequestWebViewRequest(
                    peer='mrkt',
                    bot='mrkt',
                    platform='android',
                    url=self.webapp_url
                ))

                if not result.url:
                    logger.warning("No URL in MRKT WebView response")
                    return False

                # Parse init data from URL fragment
                parsed = urllib.parse.urlparse(result.url)
                fragment = parsed.fragment or ""

                if 'tgWebAppData=' in fragment:
                    # Extract tgWebAppData value
                    params = urllib.parse.parse_qs(fragment)
                    if 'tgWebAppData' in params:
                        self._init_data = params['tgWebAppData'][0]
                        # Init data is valid for ~1 hour, refresh every 30 min
                        self._init_data_expires = time.time() + 1800
                        logger.info("MRKT init data refreshed")
                        return True

                logger.warning("Could not parse MRKT init data from URL")
                return False

            except Exception as e:
                logger.error(f"Failed to get MRKT init data: {e}")
                return False

    async def get_listing_id(self, slug: str) -> Optional[str]:
        """Get MRKT listing ID by gift slug.

        Args:
            slug: Gift slug (e.g., "jesterhat-116087")

        Returns:
            MRKT listing UUID for startapp parameter, or None if not found.
        """
        # Check cache first
        if slug in self._cache:
            listing_id, timestamp = self._cache[slug]
            if time.time() - timestamp < self._cache_ttl:
                return listing_id

        # Ensure we have auth
        if not await self._refresh_init_data():
            logger.debug("Could not get MRKT auth")
            return None

        try:
            session = await self._get_session()

            # Parse slug to get collection name and number
            parts = slug.rsplit("-", 1)
            if len(parts) != 2:
                return None

            collection_slug, number_str = parts
            try:
                number = int(number_str)
            except ValueError:
                return None

            # Convert slug to collection name (e.g., "jesterhat" -> "Jester Hat")
            collection_name = collection_slug.replace("-", " ").title()
            # Handle special cases
            collection_name = collection_name.replace("Tophat", "Top Hat")

            # Query MRKT API
            headers = {
                "Authorization": f"tma {self._init_data}",
                "Content-Type": "application/json"
            }

            payload = {
                "page": 0,
                "limit": 100,
                "collectionNames": [collection_name],
            }

            async with session.post(
                f"{self.api_url}/gifts/saling",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    gifts = data.get("gifts", [])

                    # Find the gift with matching number
                    for gift in gifts:
                        if gift.get("number") == number:
                            listing_id = gift.get("id")
                            if listing_id:
                                self._cache[slug] = (listing_id, time.time())
                                logger.debug(f"Found MRKT listing {slug}: {listing_id}")
                                return listing_id

                    logger.debug(f"Gift {slug} not in MRKT listings ({len(gifts)} checked)")
                    return None
                elif resp.status == 401:
                    # Auth expired, clear it
                    self._init_data = None
                    self._init_data_expires = 0
                    logger.warning("MRKT auth expired")
                    return None
                else:
                    logger.warning(f"MRKT API error: {resp.status}")
                    return None

        except Exception as e:
            logger.error(f"Error getting MRKT listing for {slug}: {e}")
            return None

    async def close(self):
        """Close HTTP session (Telegram client is shared)."""
        if self._session and not self._session.closed:
            await self._session.close()


# Global instance
mrkt_api = MRKTApiService()
