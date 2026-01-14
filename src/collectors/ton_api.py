"""TON API collector for on-chain gift NFT data."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Awaitable, Dict, List
import aiohttp
from src.config import settings
from src.core.models import MarketEvent, EventType, EventSource

logger = logging.getLogger(__name__)


# TON Gift NFT Collection addresses
GIFT_COLLECTIONS = {
    "Plush Pepes": "EQBG-g6ahkAUGWpefWbx-D_9sQ8oWbvy6puuq78U2c4NUDFS",
    "Easter Eggs": "EQAwnP7dGfE_WO0xiCiulkAXUG1K1bWH1vE1k64T4G-7gruO",
    "Swiss Watches": "EQBI07PXew94YQz7GwN72nPNGF6htSTOJkuU4Kx_bjTZv32U",
    "Toy Bears": "EQC1gud6QO8NdJjVrqr7qFBMO0oQsktkvzhmIRoMKo8vxiyL",
    "Lol Pops": "EQC6zjid8vJNEWqcXk10XjsdDLRKbcPZzbHusuEW6FokOWIm",
    "Eternal Candles": "EQBzZLNIr4lie0pTfrbRsANJOtFYwY5gmngRfs84Ras5-aVN",
    "Stellar Rockets": "EQDIruSTyxvq60gUH8j2kkj3qzoBrBaJy9WkKbeNNRasWe4j",
    "Durov's Caps": "EQD9ikZq6xPgKjzmdBG0G0S80RvUJjbwgHrPZXDKc_wsE84w",
    "Astral Shards": "EQCBR3HaX5Cg0t2j1F9EzMNwLWKjQ4eyN-Cda7B1CWHVkNOh",
    "Jelly Bunnies": "EQA1jXaRixNn7VWw3sI8BqLHOUbnY6yfFZ7QMv8M7N_q9JJu",
    "Skull Flowers": "EQABdV2_I95vBh8rDfGq6I7v-BmA9yMH_Z8osCOL6O1rZtKS",
    "Desert Spirits": "EQAvd44wd_ho2-J8dJB-PI0LT8yH0bZ6_mVPtQujbZvzCGS4",
    "Magic Potions": "EQBiuIcEBjzOC0bOEnq0tFd6-5jELbB3gRTKcZMVqt9qb3gf",
    "Crystal Balls": "EQCnJe_GMLJ0_ZjXiAbCPdJDdMDPjR2eLb-Nn7MVXQ6QdP2w",
    "Voodoo Dolls": "EQAH9z-cJb3TLkHXSaB0hF3q3Q9FPxFGPBkJ6PkHJ2dPKf_n",
    "Sakura Blooms": "EQD0CAq6P34Ga7ycb0zM38OG-O-XaHWBKOQKbDXP_QMKhJhg",
    "Ginger Cookies": "EQBo8pAkT8w2_C9HYQx5o1YX2FbKcwO1EInGDHl8XkJYJp9c",
    "Top Hats": "EQDnMo8F3Kla-M5bnz1_f9aW1YX-hzjG8oSuN7q4lhZ5aPND",
    "Ion Stars": "EQBf2fIvzzA1XQNq0HRlWU6qJnKV3GZ9lP7qP3X-IKCbsxKb",
    "Gem Stones": "EQC8tKkz8lRu4h6b7BWn6gFqjFN9_n6pNE3H0z5K_kKPT-Sm",
    "Heart Flames": "EQBVg8Wh-PvLcZP5jU2JUNq1fP3lLJT1Q3Tl3r8X4VRi0KMP",
    "Christmas Stars": "EQDShJvpYf0NuydB-AXGFm3bNUkN0G3mJeB9Xqb_4rVT_CVz",
    "Warm Socks": "EQArkJC2Lh6tl4tN9dRhM8fUB4bHp8PCCp3iP-TDJqCFKsQJ",
    "Lucky Clovers": "EQDz8Ia5_uN4B1J8JsMiKQyJl4QD9aXQ6XVjPvLF-LgCFg0Y",
    "Electric Skulls": "EQBgCFijNkKn7v-SuPDfqD4p7jJ2fL5w3Jp8O0VnY7N-E4hz",
    "Space Bottles": "EQAn9Kq4p5dJn0mL8U9vFHy1MuC8LZ8a9Qk3s_FT-bCVJT0e",
    "Record Players": "EQB0F7pVnT5z4Q6QwY3qLJmnR6H8gCXjKFm9M5l2bvN_KJhc",
    "Party Sparklers": "EQCj5Xd3DfVBz8HKyMN5qT9XaJhR4kW1gQp7mF-nYR2_cXLh",
    "Snow Globes": "EQAugUOx4HPbSlDAnqf0YdjFSR3lB7mT9qJzPDVmIJhNOTUU",
    "Bunnycorns": "EQBTzKflLdF3NVQC1qQh7WR8Mq2P9HgJlKd2mLvNbU5_4jXY",
    "Homemade Cakes": "EQDvmM_Kzua9TNa1w8XPrVRl0HYyqT7J-Zq3Nb5P9dQHfCYP",
    "Spiced Wines": "EQC0Yjf8PmNv_tL3xQB4Z5JqD9hK_MW2nRp6mY-FT1vCqXhR",
    "Love Candles": "EQBt7HjP5D4a_W8nXLdQ9KrMvZy1JEf3N2qT_pF-6dYVbTkO",
    "Hanging Stars": "EQANp3bfJLxY-0qT7KHdWm5MRZv2nG4jQ9FhC8XE_1pYaLDh",
    "Signet Rings": "EQC5F8jK2Xb_fN0mPQHdV4Lrq3pT9MW1JYk6n2-ZG_vBhKXc",
    "Trapped Hearts": "EQAmfQdP3LyZ0bV8JKNn5TqMhH2W4GdX1pFk7rCvT9Y_cEtO",
    "Perfume Bottles": "EQBHkd7aP5Lz_W2nYQm1KvT8JXb0MRZq3NH4gcFE_6pCfVxY",
    "B-Day Candles": "EQAQBZ2jN8xL0fVqKP3dYTm5Hv_7MWz4n1Gh9FC_rEXbpKtO",
    "Vintage Cigars": "EQCjXp2bM9aZ_v8nTKNqFhd3P0Lr1YQk7Wm4JC_ZGE5HcfVx",
    "Diamond Rings": "EQAhkLf5Nb_v9T8mXQYd1pPKrJz0M2WHn4Gq3CF_ZEV7aBtO",
    "Precious Peaches": "EQD8kT3bN_Lz0fVmJXYdWqKPHp5a1MRQ7n2Gh4FC_ZECxpVt",
}


class TonApiCollector:
    """Collector for TON blockchain NFT gift data."""

    def __init__(self):
        self.base_url = settings.TON_API_BASE_URL
        self.api_key = settings.TON_API_KEY
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.event_handler: Optional[Callable[[MarketEvent], Awaitable[None]]] = None
        # Track last processed event timestamp for each collection
        self.last_lt: Dict[str, int] = {}
        self.processed_events: set = set()
        self.max_event_cache = 5000
        self.api_available = True

    async def start(self, event_handler: Callable[[MarketEvent], Awaitable[None]]):
        """Start collecting on-chain events."""
        self.event_handler = event_handler
        self.running = True

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.session = aiohttp.ClientSession(headers=headers)
        logger.info(f"TON API collector started, tracking {len(GIFT_COLLECTIONS)} collections")

        # Start polling for all collections
        await self._poll_all_collections()

    async def stop(self):
        """Stop collecting events."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("TON API collector stopped")

    async def _poll_all_collections(self):
        """Poll all gift collections for events."""
        poll_interval = 10  # Poll every 10 seconds (more conservative for blockchain data)

        while self.running:
            try:
                # Process collections in batches to avoid rate limits
                collection_items = list(GIFT_COLLECTIONS.items())

                for gift_name, collection_address in collection_items:
                    if not self.running:
                        break

                    try:
                        await self._poll_collection_events(gift_name, collection_address)
                    except Exception as e:
                        logger.error(f"Error polling {gift_name}: {e}")

                    # Small delay between collections to respect rate limits
                    await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in TON API poll loop: {e}")

            await asyncio.sleep(poll_interval)

    async def _poll_collection_events(self, gift_name: str, collection_address: str):
        """Poll events for a specific collection."""
        # Use the accounts events endpoint to get NFT sales
        endpoint = f"{self.base_url}/v2/accounts/{collection_address}/events"

        params = {
            "limit": 50,
            "subject_only": "false",
        }

        # Add start_date parameter if we have a last lt
        if collection_address in self.last_lt:
            params["start_lt"] = self.last_lt[collection_address]

        try:
            async with self.session.get(endpoint, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if not self.api_available:
                        logger.info("TON API recovered!")
                        self.api_available = True

                    events = data.get("events", [])
                    await self._process_events(events, gift_name, collection_address)

                elif response.status == 429:
                    # Rate limited - back off
                    logger.warning("TON API rate limited, backing off...")
                    await asyncio.sleep(5)
                else:
                    if self.api_available:
                        logger.error(f"TON API error: {response.status}")
                        self.api_available = False

        except aiohttp.ClientError as e:
            logger.error(f"TON API connection error: {e}")

    async def _process_events(self, events: List[dict], gift_name: str, collection_address: str):
        """Process events from TON API."""
        for event_data in events:
            try:
                event_id = event_data.get("event_id")

                if event_id in self.processed_events:
                    continue

                # Track lt for pagination
                lt = event_data.get("lt")
                if lt:
                    current_lt = self.last_lt.get(collection_address, 0)
                    if lt > current_lt:
                        self.last_lt[collection_address] = lt

                # Parse event
                market_event = self._parse_event(event_data, gift_name)

                if market_event:
                    self.processed_events.add(event_id)

                    # Clean cache if needed
                    if len(self.processed_events) > self.max_event_cache:
                        # Remove half of oldest entries
                        to_remove = list(self.processed_events)[: self.max_event_cache // 2]
                        for item in to_remove:
                            self.processed_events.discard(item)

                    # Send to handler
                    if self.event_handler:
                        await self.event_handler(market_event)

            except Exception as e:
                logger.error(f"Error processing TON event: {e}")

    def _parse_event(self, event_data: dict, gift_name: str) -> Optional[MarketEvent]:
        """Parse TON API event into MarketEvent."""
        try:
            # Get event actions
            actions = event_data.get("actions", [])

            for action in actions:
                action_type = action.get("type")

                # We're interested in NFT transfers (sales) and NFT listings
                if action_type == "NftItemTransfer":
                    return self._parse_nft_transfer(action, event_data, gift_name)
                elif action_type == "NftPurchase":
                    return self._parse_nft_purchase(action, event_data, gift_name)

            return None

        except Exception as e:
            logger.error(f"Failed to parse TON event: {e}")
            return None

    def _parse_nft_transfer(
        self, action: dict, event_data: dict, gift_name: str
    ) -> Optional[MarketEvent]:
        """Parse NFT transfer action."""
        try:
            nft_transfer = action.get("NftItemTransfer", {})
            nft = nft_transfer.get("nft")

            if not nft:
                return None

            # Get NFT address as gift_id
            nft_address = nft.get("address") or nft_transfer.get("nft")

            if not nft_address:
                return None

            # Get price from event (if it was a sale)
            # TON transfers with value indicate a sale
            value_data = action.get("value") or event_data.get("value_flow", {})
            price_nano = 0

            if isinstance(value_data, dict):
                # Try to extract TON amount
                price_nano = value_data.get("ton", {}).get("value", 0)
            elif isinstance(value_data, int):
                price_nano = value_data

            # Convert from nanoTON to TON
            price = Decimal(str(price_nano)) / Decimal("1000000000")

            # Skip zero-price transfers (not sales)
            if price <= 0:
                return None

            # Parse timestamp
            timestamp = event_data.get("timestamp", 0)
            event_time = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()

            # Extract NFT metadata
            metadata = nft.get("metadata", {})
            attributes = metadata.get("attributes", [])

            model = None
            backdrop = None
            pattern = None
            number = None

            for attr in attributes:
                trait_type = attr.get("trait_type", "").lower()
                value = attr.get("value")

                if trait_type == "model":
                    model = value
                elif trait_type == "backdrop":
                    backdrop = value
                elif trait_type in ("pattern", "symbol"):
                    pattern = value
                elif trait_type == "number":
                    try:
                        number = int(value)
                    except (ValueError, TypeError):
                        pass

            # Get photo URL from NFT preview
            previews = nft.get("previews", [])
            photo_url = None
            if previews:
                # Prefer larger preview
                for preview in previews:
                    if preview.get("resolution") == "500x500":
                        photo_url = preview.get("url")
                        break
                if not photo_url and previews:
                    photo_url = previews[0].get("url")

            return MarketEvent(
                event_time=event_time,
                event_type=EventType.BUY,  # Transfer with value = sale
                gift_id=nft_address,
                gift_name=gift_name,
                model=model or gift_name,
                backdrop=backdrop,
                pattern=pattern,
                number=number,
                price=price,
                photo_url=photo_url,
                source=EventSource.TON_API,
                raw_data=event_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse NFT transfer: {e}")
            return None

    def _parse_nft_purchase(
        self, action: dict, event_data: dict, gift_name: str
    ) -> Optional[MarketEvent]:
        """Parse NFT purchase action (from marketplaces like GetGems)."""
        try:
            purchase = action.get("NftPurchase", {})
            nft = purchase.get("nft", {})

            nft_address = nft.get("address")
            if not nft_address:
                return None

            # Get price
            amount = purchase.get("amount", {})
            price_nano = amount.get("value", 0) if isinstance(amount, dict) else int(amount or 0)
            price = Decimal(str(price_nano)) / Decimal("1000000000")

            if price <= 0:
                return None

            # Parse timestamp
            timestamp = event_data.get("timestamp", 0)
            event_time = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()

            # Extract NFT metadata
            metadata = nft.get("metadata", {})
            attributes = metadata.get("attributes", [])

            model = None
            backdrop = None
            pattern = None
            number = None

            for attr in attributes:
                trait_type = attr.get("trait_type", "").lower()
                value = attr.get("value")

                if trait_type == "model":
                    model = value
                elif trait_type == "backdrop":
                    backdrop = value
                elif trait_type in ("pattern", "symbol"):
                    pattern = value
                elif trait_type == "number":
                    try:
                        number = int(value)
                    except (ValueError, TypeError):
                        pass

            # Get photo URL
            previews = nft.get("previews", [])
            photo_url = None
            if previews:
                for preview in previews:
                    if preview.get("resolution") == "500x500":
                        photo_url = preview.get("url")
                        break
                if not photo_url and previews:
                    photo_url = previews[0].get("url")

            return MarketEvent(
                event_time=event_time,
                event_type=EventType.BUY,
                gift_id=nft_address,
                gift_name=gift_name,
                model=model or gift_name,
                backdrop=backdrop,
                pattern=pattern,
                number=number,
                price=price,
                photo_url=photo_url,
                source=EventSource.TON_API,
                raw_data=event_data,
            )

        except Exception as e:
            logger.error(f"Failed to parse NFT purchase: {e}")
            return None

    async def get_collection_items(self, collection_address: str, limit: int = 100) -> List[dict]:
        """Get NFT items from a collection (for listings snapshot)."""
        endpoint = f"{self.base_url}/v2/nfts/collections/{collection_address}/items"

        params = {"limit": limit}

        try:
            async with self.session.get(endpoint, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("nft_items", [])
        except Exception as e:
            logger.error(f"Error fetching collection items: {e}")

        return []

    async def get_nft_history(self, nft_address: str) -> List[dict]:
        """Get transaction history for a specific NFT."""
        endpoint = f"{self.base_url}/v2/nfts/{nft_address}/history"

        try:
            async with self.session.get(endpoint) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("events", [])
        except Exception as e:
            logger.error(f"Error fetching NFT history: {e}")

        return []
