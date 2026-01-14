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


# TON Gift NFT Collection addresses (raw format 0:...)
# Verified from tonapi.io search
GIFT_COLLECTIONS = {
    # Verified collections from Fragment/Telegram
    "Plush Pepes": "0:46fa0e9a864014196a5e7d66f1f83ffdb10f2859bbf2ea9baeabbf14d9ce0d50",
    "Snoop Doggs": "0:28270ec1a4e7010f7cbdbe832e110faa852dcae20b4cfba11e3cbc64ce4f224a",
    "Durov's Caps": "0:fd8a466aeb13e02a3ce67411b41b44bcd11bd42636f0807acf6570ca73fc2c13",
    "Lol Pops": "0:bace389df2f24d116a9c5e4d745e3b1d0cb44a6dc3d9cdb1eeb2e116e85a2439",
    "Witch Hats": "0:43f1a04a0b836c9d832ab6409f3d09361159e27b29c9429d54819572c7556647",
    "Homemade Cakes": "0:9e7eb8e1083dbfec7448af6966c2df596aa786fed76c781bc00c2ebaf37de405",
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

            # Handle both string address and object formats
            if isinstance(nft, str):
                nft_address = nft
                nft = {}  # Empty dict for metadata extraction
            else:
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
