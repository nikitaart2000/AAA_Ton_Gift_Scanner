"""GiftAsset API client for OSINT and market data.

This service provides access to GiftAsset's comprehensive gift database,
which has historical data about gift ownership, transfers, and market activity.

IMPORTANT: Use sparingly! This is a test API key.
- get_gift_by_name: DON'T call frequently (expensive endpoint)
- Other endpoints: Can be used normally but with rate limiting
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)

# GiftAsset API configuration
GIFTASSET_BASE_URL = "https://giftasset.pro/api/v1/gifts"


@dataclass
class GiftAssetGift:
    """Gift data from GiftAsset API."""
    name: str
    collection: str
    model: Optional[str] = None
    backdrop: Optional[str] = None
    pattern: Optional[str] = None
    number: Optional[int] = None
    rarity: Optional[str] = None
    floor_price: Optional[float] = None
    owner_username: Optional[str] = None


@dataclass
class UserGiftSummary:
    """Summary of user's gift collection from GiftAsset."""
    username: str
    total_gifts: int
    total_value: float
    collections: dict[str, int]  # collection_name -> count
    gifts: list[GiftAssetGift]


@dataclass
class MarketSale:
    """Recent market sale from GiftAsset."""
    collection: str
    model: Optional[str]
    price: float
    provider: str
    timestamp: datetime
    gift_name: Optional[str] = None


class GiftAssetAPI:
    """
    Client for GiftAsset API.

    Provides OSINT data about Telegram gift ownership and market activity.
    This data complements our own collected data with historical information.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = GIFTASSET_BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limiter = asyncio.Semaphore(2)  # Max 2 concurrent requests
        self._last_request_time = 0.0
        self._min_request_interval = 0.5  # 500ms between requests

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        now = asyncio.get_event_loop().time()
        time_since_last = now - self._last_request_time
        if time_since_last < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None
    ) -> Optional[dict]:
        """Make a rate-limited request to GiftAsset API."""
        async with self._rate_limiter:
            await self._rate_limit()

            session = await self._get_session()
            url = f"{self.base_url}/{endpoint}"

            try:
                if method == "GET":
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 401:
                            logger.error("GiftAsset API: Invalid API key")
                        elif resp.status == 404:
                            logger.debug(f"GiftAsset API: Not found - {endpoint}")
                        else:
                            logger.warning(f"GiftAsset API error {resp.status}: {await resp.text()}")
                else:  # POST
                    async with session.post(url, params=params, json=json_data) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 401:
                            logger.error("GiftAsset API: Invalid API key")
                        else:
                            logger.warning(f"GiftAsset API error {resp.status}: {await resp.text()}")
            except Exception as e:
                logger.error(f"GiftAsset API request failed: {e}")

            return None

    # ==================== User OSINT Endpoints ====================

    async def get_user_gifts(
        self,
        username: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[GiftAssetGift]:
        """
        Get all gifts owned by a user.

        This is the primary OSINT endpoint for looking up someone's gifts.
        """
        # Remove @ if present
        username = username.lstrip("@")

        data = await self._request(
            "GET",
            "get_gift_by_user",
            params={"username": username, "limit": limit, "offset": offset}
        )

        if not data:
            return []

        gifts = []
        for item in data:
            try:
                # Parse the gift data
                gift = GiftAssetGift(
                    name=item.get("name", ""),
                    collection=item.get("collection_name", ""),
                    model=item.get("model"),
                    backdrop=item.get("backdrop"),
                    pattern=item.get("pattern"),
                    number=item.get("number"),
                    rarity=item.get("rarity"),
                    floor_price=item.get("floor_price"),
                    owner_username=username,
                )
                gifts.append(gift)
            except Exception as e:
                logger.debug(f"Failed to parse gift: {e}")

        return gifts

    async def get_user_collections_summary(
        self,
        username: str,
        limit: int = 100
    ) -> dict[str, int]:
        """
        Get summary of user's collections (collection name -> count).

        Faster than get_user_gifts when you just need counts.
        """
        username = username.lstrip("@")

        data = await self._request(
            "POST",
            "get_all_collections_by_user",
            params={"username": username},
            json_data={"limit": limit, "offset": 0}
        )

        if not data:
            return {}

        return {item["collection_name"]: item["count"] for item in data}

    async def get_user_profile_value(
        self,
        username: str,
        limit: int = 100
    ) -> Optional[float]:
        """
        Get total estimated value of user's gift profile.
        """
        username = username.lstrip("@")

        data = await self._request(
            "GET",
            "get_user_profile_price",
            params={"username": username, "limit": limit}
        )

        if not data:
            return None

        # The response has totals
        return data.get("total_price") or data.get("total")

    async def get_full_user_summary(self, username: str) -> Optional[UserGiftSummary]:
        """
        Get comprehensive summary of a user's gifts.

        Combines multiple API calls for full OSINT report.
        """
        username = username.lstrip("@")

        # Get gifts and collections in parallel
        gifts_task = self.get_user_gifts(username, limit=200)
        collections_task = self.get_user_collections_summary(username)
        value_task = self.get_user_profile_value(username)

        gifts, collections, value = await asyncio.gather(
            gifts_task, collections_task, value_task
        )

        if not gifts and not collections:
            return None

        return UserGiftSummary(
            username=username,
            total_gifts=len(gifts),
            total_value=value or 0.0,
            collections=collections,
            gifts=gifts,
        )

    # ==================== Market Data Endpoints ====================

    async def get_floor_prices(self, include_models: bool = False) -> Optional[dict]:
        """
        Get current floor prices for all collections.
        """
        return await self._request(
            "GET",
            "get_gifts_price_list",
            params={"models": str(include_models).lower()}
        )

    async def get_recent_sales(
        self,
        collection: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 50
    ) -> list[MarketSale]:
        """
        Get recent unique gift sales.
        """
        params = {"limit": limit}
        if collection:
            params["collection_name"] = collection
        if model:
            params["model_name"] = model

        data = await self._request("GET", "get_unique_last_sales", params=params)

        if not data:
            return []

        sales = []
        for item in data:
            try:
                sale = MarketSale(
                    collection=item.get("collection_name", ""),
                    model=item.get("model"),
                    price=float(item.get("price", 0)),
                    provider=item.get("provider", ""),
                    timestamp=datetime.fromisoformat(item["timestamp"]) if "timestamp" in item else datetime.now(),
                    gift_name=item.get("gift_name"),
                )
                sales.append(sale)
            except Exception as e:
                logger.debug(f"Failed to parse sale: {e}")

        return sales

    async def get_best_deals(self) -> Optional[dict]:
        """
        Get top deals of the day across all providers.
        """
        return await self._request("GET", "get_top_best_deals")

    async def get_collection_marketcap(self) -> Optional[dict]:
        """
        Get market cap data for all collections.
        """
        return await self._request("GET", "get_gifts_collections_marketcap")

    async def get_provider_volumes(self) -> Optional[dict]:
        """
        Get sales volume statistics per provider.
        """
        return await self._request("GET", "get_providers_volumes")

    async def get_collection_health(self) -> Optional[dict]:
        """
        Get health index for all collections (liquidity, concentration, etc).
        """
        return await self._request("GET", "get_gifts_collections_health_index")

    # ==================== Careful Use Endpoints ====================

    async def get_gift_details(self, gift_name: str) -> Optional[dict]:
        """
        Get detailed information about a specific gift.

        ⚠️ WARNING: Don't call this frequently! It's expensive.
        Use only when absolutely necessary.
        """
        logger.warning(f"GiftAsset: get_gift_by_name called for {gift_name} - use sparingly!")

        return await self._request(
            "GET",
            "get_gift_by_name",
            params={"name": gift_name}
        )

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()


# Global instance (will be initialized with API key from settings)
_giftasset_api: Optional[GiftAssetAPI] = None


def get_giftasset_api() -> Optional[GiftAssetAPI]:
    """Get the global GiftAsset API instance."""
    global _giftasset_api

    api_key = getattr(settings, "GIFTASSET_API_KEY", None)
    if not api_key:
        return None

    if _giftasset_api is None:
        _giftasset_api = GiftAssetAPI(api_key)

    return _giftasset_api
