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
# Extracted from gift-minter.ton transaction history
# Total: 61+ collections (more may be added as new gifts launch)
GIFT_COLLECTIONS = {
    # Premium/Rare Collections
    "Plush Pepes": "0:46fa0e9a864014196a5e7d66f1f83ffdb10f2859bbf2ea9baeabbf14d9ce0d50",
    "Snoop Doggs": "0:28270ec1a4e7010f7cbdbe832e110faa852dcae20b4cfba11e3cbc64ce4f224a",
    "Durov's Caps": "0:fd8a466aeb13e02a3ce67411b41b44bcd11bd42636f0807acf6570ca73fc2c13",
    "Witch Hats": "0:43f1a04a0b836c9d832ab6409f3d09361159e27b29c9429d54819572c7556647",
    "Eternal Roses": "0:ee9b2ddb9d96335786d258c492664997ab1e745ee1f977d4655ffc848b614d96",
    "Diamond Rings": "0:9687594f96dc93c025b10979b8ba62f9b4f6685d1f244c8713fa977426aa1a74",
    "Swiss Watches": "0:48d3b3d77b0f78610cfb1b037bda73cd185ea1b524ce264b94e0ac7f6e34d9bf",
    "Khabib's Papakhas": "0:ec899ba58909ff15351ec8255a561a2396363b2e68a6754b492b54a7b464f37d",
    "Snoop Cigars": "0:3bd947afaff307bf36304821c950afae0ba91dfb0f246f1ce1278f562221bea3",
    "Vintage Cigars": "0:02710a51d9f99d784356744d98190587571493c80f19ab8fe4eeb93f21ac4245",
    "UFC Strikes": "0:da8f5f1c77ad552d91c21ec33bb0a6dfc41b9d0f781a49f70dd36a2556743704",

    # Regular Collections
    "Artisan Bricks": "0:36448ed7bc8b3dc0940aaf19136fb62da5e52e683fa9d1e4f9b817b86e47064f",
    "B-Day Candles": "0:b01057d46db47edb67e7dd583152906297b6f0050a841e6ef081061b598f5cd3",
    "Big Years": "0:f1f92a901213fd4737e2d9ca9d7a14d552f41b02bb14cf55fbb7eba5f0888a66",
    "Bling Binkies": "0:11200ba6196066292bf6068331b6e9c2105c9b227ea78a60aafe569eaa40fe01",
    "Bonded Rings": "0:8c06079134e8d9a3a03f1a91781bae954c0f15e2fa528ad219cc93f7433e193b",
    "Candy Canes": "0:cb33ae6dd2c852ee064083494c96d187621b14f783f3b0c24785889b99157b91",
    "Clover Pins": "0:171d6f4a5586200e62da50d720ccd3d9e162867a4f7bfa576c7747cf5078382b",
    "Cookie Hearts": "0:53f4f6d9051e8519c6414a7c20a3e0cba5cd2beff5fff1d9611b9500eaff65f6",
    "Cupid Charms": "0:342418950a3760aa48878989888135016d923a98d6e74b29aa7f41c50bb161c6",
    "Easter Eggs": "0:309cfedd19f13f58ed318828ae964017506d4ad5b587d6f13593ae13e06fbb82",
    "Evil Eyes": "0:d0e838d169b4d8480c5fdb1ad9b27b17b6a7089b56e3f5d179c7f87c94d8d63e",
    "Faith Amulets": "0:fdcfcee1459015ec2d8c575824dfdf9b4a0e587ecd8474cafd1df2bcd48b81d9",
    "Fresh Socks": "0:147df416974f7fca15c34e9f28375dcfc7cca03e6d317323468473a238d57ec7",
    "Ginger Cookies": "0:427bbe46d00863a82eb807b1ff0473f4c207ce357ff1f7caecce6b04c2774354",
    "Holiday Drinks": "0:793f764fd8f8cb20e379d98d52340bb1d5da38f993aa316a2d5d2f9f74ca6a1d",
    "Homemade Cakes": "0:9e7eb8e1083dbfec7448af6966c2df596aa786fed76c781bc00c2ebaf37de405",
    "Ice Creams": "0:54bec904be659da7f57a1d7fb64f27e9e26152ccccdd83d4da533eb3295cfa3a",
    "Input Keys": "0:5220877bb0c9a5a8df2804668c36d51eb9a2de4903d4475072330a677d62f786",
    "Instant Ramens": "0:488f4b85faa2004aabfaa88bdc4e27f6c0a49db7859073899ca01cb0369e469e",
    "Jelly Bunnies": "0:30cee6dea09c27aa6981b933e99d44aead1cd63c1f0447371fcf1e7967662313",
    "Jingle Bells": "0:9e86b919b4a0ed55ed2acaf040b2b1f1de15be86ba10c83ad2fcc64e39562d87",
    "Jolly Chimps": "0:9e4d224e3d73ff492bce8c82d8fa4ba2e1b187526b1af94ed35cfe038d400d4e",
    "Joyful Bundles": "0:8170c3e9123289cac4dbe77e0dbeddc55d0824cd5ca169a043232adc68a0f53e",
    "Light Swords": "0:d1adfc39a60202e1ee8d69f500c79d99f589baab5936eb1c5a5d1feac742ca24",
    "Lol Pops": "0:bace389df2f24d116a9c5e4d745e3b1d0cb44a6dc3d9cdb1eeb2e116e85a2439",
    "Loot Bags": "0:84f340259fc61f95d9d02f058cbce7e5a0b1a098f6347860c9cfdb9f1b7811ba",
    "Love Candles": "0:ea1f04b353823f538e2f48cf440cfe07186296cbdc968dbce4a426b72bc88c04",
    "Love Potions": "0:fbc83bb658281df54cf1d5d17f0d09162bb219249e0ca7d33d835ac651489013",
    "Lunar Snakes": "0:b696c532d522b1244241c23e5909f5672cfbc0a83ab2e5cdba5e0f314bfa434d",
    "Lush Bouquets": "0:3694772f6565bf6cdff634c2ab90452ff71cfa7f1f304c4e6ea5af2ed677996f",
    "Money Pots": "0:4cdd4d6dc168c8fef61468f74593366cd6af5cd28ac78508f1d26d976bd96381",
    "Moon Pendants": "0:bba0f6be8090d9e894705b4596e161ff5639fb8a82a67c374522d0fb9d814675",
    "Nail Bracelets": "0:198ee50999b3fe578472a308dec61edb21c74daeba23af458a4a9760801d336e",
    "Pet Snakes": "0:412d116d0bfdcf2f1369597e677dc8706a993b796706dddccaa316d5e9c5b3a9",
    "Pretty Posies": "0:341334585f9c26feae3afcd5fc6fb11886d3a45df5e0b2bd3a1136e8bf56bb4a",
    "Sakura Flowers": "0:8305b4186efde7f754f0cb00510fd62b24db8d5666c3dd2a6ba6aea15880c756",
    "Santa Hats": "0:1a4c847ba09ca8c038ae9982d5374a1eeb590613723a10f127ed68073c6b9601",
    "Signet Rings": "0:ab180f6c942a24b200fe3724438ed1f248a3744ecf24ea176e78991491965d0f",
    "Sky Stilettos": "0:24a9b53092e172e6c8248171064abf564b19dbb25542736e518bd05f0042335c",
    "Sleigh Bells": "0:5c3713024f210791c43970addf3bfdc46e37fa25c039249fce255e27a4337eeb",
    "Snake Boxes": "0:5b50ac7909a944972d937a40cd7856efe1ed36a63eb1b00a9764fd17fc0a6b2a",
    "Snow Mittens": "0:0833ee50cd9197613499475446793da0f6b36962634f434f7f1edbda2271da4f",
    "Spring Baskets": "0:99e3e87ae624e25833d13dc2e54bade06dc4b8d1805a74414b0385be88859466",
    "Spy Agarics": "0:fa987f5bc1b9fa4b733fb424563afa80216f0cdf8911c1b234d678862d13de0c",
    "Star Notepads": "0:405d1ebc7f55204614e8151fdb5d8d733c9cb93bab26d92b740914e8f76053c4",
    "Stellar Rockets": "0:c8aee493cb1beaeb48141fc8f69248f7ab3a01ac1689cbd5a429b78d3516ac59",
    "Swag Bags": "0:a0693c5bdb003fdc18bc11ce0514dbbc09aba81e8d153e99f0c5dae10203ab39",
    "Tama Gadgets": "0:3f931d963b27575b361460ed433fcd1a1e5e328652c6621c633c0b513cd8cc81",
    "Top Hats": "0:03bc9c4cc421c0edf465623a1c7813917fb4702acd2bce355a29ea5000232767",
    "Toy Bears": "0:b582e77a40ef0d7498d5aeaafba8504c3b4a10b24b64bf3866211a0c2a8f2fc6",
    "Whip Cupcakes": "0:28fec9c0a430ea17a18a574c5efd3e687b6f2bf38da026d8269203cc857d3e75",
    "Winter Wreaths": "0:bc5955bd0d23783cf7c59425b60072645f10541c116cbe7857898a924e90fbb5",
    "Xmas Stockings": "0:f3fd579c12b1014cb393891d6dab4552de566e1c7aa16268596ed85cadb164ef",
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
            # TON API uses X-API-Key header, not Bearer token
            headers["X-API-Key"] = self.api_key

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
