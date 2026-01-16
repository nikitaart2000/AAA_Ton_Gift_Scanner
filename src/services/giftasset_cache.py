"""GiftAsset cache service for floor prices, rarity, and market data.

This service periodically fetches and caches data from GiftAsset API,
so we can enrich our real-time alerts with rarity scoring and arbitrage detection.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.services.giftasset_api import get_giftasset_api

logger = logging.getLogger(__name__)


@dataclass
class ProviderFloor:
    """Floor price from a specific provider."""
    collection_floor: Optional[Decimal] = None
    model_floor: Optional[Decimal] = None


@dataclass
class MarketFloorData:
    """Aggregated floor data across all providers."""
    min_floor: Optional[Decimal] = None
    max_floor: Optional[Decimal] = None
    avg_floor: Optional[Decimal] = None
    providers: dict[str, ProviderFloor] = field(default_factory=dict)


@dataclass
class RarityData:
    """Rarity information for a gift combination."""
    base_score: float = 0.0
    final_score: float = 0.0
    tier: str = "Unknown"
    flags: list[str] = field(default_factory=list)
    has_premium_attribute: bool = False


@dataclass
class BestDeal:
    """Best deal from GiftAsset."""
    gift_name: str
    collection: str
    model: Optional[str]
    price: Decimal
    provider: str
    rarity: RarityData
    market_floor: MarketFloorData
    discount_pct: Optional[Decimal] = None  # vs avg market floor


class GiftAssetCache:
    """Cache for GiftAsset market data.

    Periodically refreshes:
    - Floor prices (per collection/model, per provider)
    - Best deals (top arbitrage opportunities)
    - Market analytics
    """

    def __init__(self):
        self._floor_prices: dict[str, MarketFloorData] = {}  # collection:model -> data
        self._collection_floors: dict[str, Decimal] = {}  # collection -> floor
        self._best_deals: list[BestDeal] = []
        self._last_update: Optional[datetime] = None
        self._running = False
        self._update_task: Optional[asyncio.Task] = None
        self._update_interval = 300  # 5 minutes

    async def start(self):
        """Start the cache update loop."""
        if self._running:
            return

        api = get_giftasset_api()
        if not api:
            logger.warning("GiftAsset API not configured, cache disabled")
            return

        self._running = True
        logger.info("Starting GiftAsset cache service...")

        # Initial load
        await self._update_cache()

        # Start background refresh
        self._update_task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop the cache update loop."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("GiftAsset cache service stopped")

    async def _update_loop(self):
        """Background loop to refresh cache."""
        while self._running:
            try:
                await asyncio.sleep(self._update_interval)
                await self._update_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache update failed: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retry

    async def _update_cache(self):
        """Fetch fresh data from GiftAsset API."""
        api = get_giftasset_api()
        if not api:
            return

        try:
            logger.info("Updating GiftAsset cache...")

            # Fetch floor prices and best deals in parallel
            floor_task = api.get_floor_prices(include_models=True)
            deals_task = api.get_best_deals()

            floor_data, deals_data = await asyncio.gather(
                floor_task, deals_task, return_exceptions=True
            )

            # Process floor prices
            if isinstance(floor_data, dict) and floor_data:
                await self._process_floor_prices(floor_data)
            elif isinstance(floor_data, Exception):
                logger.error(f"Failed to fetch floor prices: {floor_data}")

            # Process best deals
            if isinstance(deals_data, dict) and deals_data:
                await self._process_best_deals(deals_data)
            elif isinstance(deals_data, Exception):
                logger.error(f"Failed to fetch best deals: {deals_data}")

            self._last_update = datetime.now(timezone.utc)
            logger.info(
                f"GiftAsset cache updated: {len(self._floor_prices)} models, "
                f"{len(self._best_deals)} deals"
            )

        except Exception as e:
            logger.error(f"Cache update error: {e}", exc_info=True)

    async def _process_floor_prices(self, data: dict):
        """Process floor prices response."""
        new_floors = {}
        new_collection_floors = {}

        for item in data if isinstance(data, list) else [data]:
            try:
                collection = item.get("collection_name", "")
                model = item.get("model_name")

                # Collection-level floor
                if collection and not model:
                    coll_floor = item.get("floor_price") or item.get("price")
                    if coll_floor:
                        new_collection_floors[collection] = Decimal(str(coll_floor))

                # Model-level floor with provider breakdown
                if collection and model:
                    key = f"{collection}:{model}"

                    market_floor = MarketFloorData()

                    # Parse provider floors if available
                    providers_data = item.get("providers", {})
                    for provider_name, provider_info in providers_data.items():
                        if isinstance(provider_info, dict):
                            pf = ProviderFloor(
                                collection_floor=Decimal(str(provider_info["collection_floor"])) if provider_info.get("collection_floor") else None,
                                model_floor=Decimal(str(provider_info["model_floor"])) if provider_info.get("model_floor") else None,
                            )
                            market_floor.providers[provider_name] = pf

                    # Parse aggregate floor
                    floor_info = item.get("market_floor", {})
                    if floor_info:
                        market_floor.min_floor = Decimal(str(floor_info["min"])) if floor_info.get("min") else None
                        market_floor.max_floor = Decimal(str(floor_info["max"])) if floor_info.get("max") else None
                        market_floor.avg_floor = Decimal(str(floor_info["avg"])) if floor_info.get("avg") else None
                    else:
                        # Fallback: use simple floor price
                        floor_price = item.get("floor_price") or item.get("price")
                        if floor_price:
                            market_floor.min_floor = Decimal(str(floor_price))

                    new_floors[key] = market_floor

            except Exception as e:
                logger.debug(f"Failed to parse floor item: {e}")

        self._floor_prices = new_floors
        self._collection_floors = new_collection_floors

    async def _process_best_deals(self, data: dict):
        """Process best deals response."""
        new_deals = []

        # Data is grouped by provider
        for provider, deals in data.items():
            if not isinstance(deals, list):
                continue

            for deal in deals:
                try:
                    gift_data = deal.get("gift", {})

                    # Parse rarity
                    rarity_data = gift_data.get("gift_rarity", {})
                    rarity = RarityData(
                        base_score=float(rarity_data.get("base_score", 0)),
                        final_score=float(rarity_data.get("final_score", 0)),
                        tier=rarity_data.get("tier", "Unknown"),
                        flags=rarity_data.get("flags", []),
                        has_premium_attribute="HasPremiumAttribute" in rarity_data.get("flags", []),
                    )

                    # Parse market floor
                    floor_info = gift_data.get("market_floor", {})
                    providers_info = gift_data.get("providers", {})

                    market_floor = MarketFloorData(
                        min_floor=Decimal(str(floor_info["min"])) if floor_info.get("min") else None,
                        max_floor=Decimal(str(floor_info["max"])) if floor_info.get("max") else None,
                        avg_floor=Decimal(str(floor_info["avg"])) if floor_info.get("avg") else None,
                    )

                    for prov_name, prov_data in providers_info.items():
                        if isinstance(prov_data, dict):
                            market_floor.providers[prov_name] = ProviderFloor(
                                collection_floor=Decimal(str(prov_data["collection_floor"])) if prov_data.get("collection_floor") else None,
                                model_floor=Decimal(str(prov_data["model_floor"])) if prov_data.get("model_floor") else None,
                            )

                    # Get price and calculate discount
                    price = Decimal(str(deal.get("price", 0)))
                    discount_pct = None
                    if market_floor.avg_floor and market_floor.avg_floor > 0:
                        discount_pct = ((market_floor.avg_floor - price) / market_floor.avg_floor) * 100

                    # Extract gift info from GiftAsset response
                    # API uses telegram_gift_name, telegram_gift_title, etc.
                    attributes = gift_data.get("attributes", {})
                    gift_name = gift_data.get("telegram_gift_name") or gift_data.get("name", "Unknown")
                    collection = gift_data.get("telegram_gift_title") or gift_data.get("collection_name", "")
                    model = attributes.get("MODEL", {}).get("value", "") if attributes else ""

                    best_deal = BestDeal(
                        gift_name=gift_name,
                        collection=collection,
                        model=model,
                        price=price,
                        provider=provider,
                        rarity=rarity,
                        market_floor=market_floor,
                        discount_pct=discount_pct,
                    )
                    new_deals.append(best_deal)

                except Exception as e:
                    logger.debug(f"Failed to parse deal: {e}")

        # Sort by discount
        new_deals.sort(key=lambda d: d.discount_pct or 0, reverse=True)
        self._best_deals = new_deals[:50]  # Keep top 50

    # ==================== Public API ====================

    def get_model_floor(self, collection: str, model: str) -> Optional[MarketFloorData]:
        """Get floor data for a specific collection:model."""
        key = f"{collection}:{model}"
        return self._floor_prices.get(key)

    def get_collection_floor(self, collection: str) -> Optional[Decimal]:
        """Get collection-level floor price."""
        return self._collection_floors.get(collection)

    def get_provider_floors(self, collection: str, model: str) -> dict[str, Decimal]:
        """Get floor prices per provider for comparison."""
        data = self.get_model_floor(collection, model)
        if not data:
            return {}

        result = {}
        for provider, pf in data.providers.items():
            if pf.model_floor:
                result[provider] = pf.model_floor
            elif pf.collection_floor:
                result[provider] = pf.collection_floor
        return result

    def get_best_deals(self, limit: int = 10) -> list[BestDeal]:
        """Get top best deals."""
        return self._best_deals[:limit]

    def get_deals_by_provider(self, provider: str, limit: int = 10) -> list[BestDeal]:
        """Get best deals for a specific provider."""
        deals = [d for d in self._best_deals if d.provider.lower() == provider.lower()]
        return deals[:limit]

    def check_arbitrage(
        self,
        collection: str,
        model: str,
        price: Decimal,
        current_provider: str
    ) -> Optional[dict]:
        """Check if there's an arbitrage opportunity.

        Returns info about cheaper prices on other providers, or None.
        """
        provider_floors = self.get_provider_floors(collection, model)
        if not provider_floors:
            return None

        # Find best (lowest) price among other providers
        best_other_price = None
        best_other_provider = None

        for provider, floor in provider_floors.items():
            if provider.lower() == current_provider.lower():
                continue
            if best_other_price is None or floor < best_other_price:
                best_other_price = floor
                best_other_provider = provider

        if not best_other_price:
            return None

        # Calculate if this is a good deal vs other providers
        if price < best_other_price:
            discount = ((best_other_price - price) / best_other_price) * 100
            return {
                "is_arbitrage": True,
                "discount_pct": discount,
                "best_other_price": best_other_price,
                "best_other_provider": best_other_provider,
                "all_provider_floors": provider_floors,
            }

        return None

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "models_cached": len(self._floor_prices),
            "collections_cached": len(self._collection_floors),
            "deals_cached": len(self._best_deals),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "is_running": self._running,
        }


# Global cache instance
giftasset_cache = GiftAssetCache()
