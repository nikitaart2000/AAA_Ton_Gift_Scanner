"""Gift Collector Worker - Background service for collecting gift data.

This worker runs 24/7 and collects:
1. NFT transfers from TON blockchain (via TonAPI SSE)
2. Public gifts from Telegram profiles
3. Wallet-username connections from NFT metadata

Over time, this builds a comprehensive database of:
- Who sent gifts to whom
- Wallet addresses linked to Telegram users
- Complete gift history for OSINT lookups
"""

import os
import asyncio
import logging
import base64
from datetime import datetime, timedelta
from typing import Optional

import aiohttp

from src.storage.gift_history import GiftHistoryService, NFTTransfer, WalletUsername
from src.services.fragment_metadata import fragment_metadata
from src.services.telegram_client import tg_client_manager

logger = logging.getLogger(__name__)

# TonAPI SSE endpoint
TONAPI_SSE_URL = "https://tonapi.io/v2/sse"
TONAPI_BASE = "https://tonapi.io/v2"

# NFT Transfer opcode (TEP-62)
NFT_TRANSFER_OPCODE = "0x5fcc3d14"


def to_raw_address(user_friendly: str) -> str:
    """Convert user-friendly TON address to raw format (workchain:hex)."""
    # Convert URL-safe base64 to standard base64
    b64 = user_friendly.replace("-", "+").replace("_", "/")
    # Add padding if needed
    while len(b64) % 4:
        b64 += "="
    # Decode
    data = base64.b64decode(b64)
    # Extract workchain (byte 1) and account id (bytes 2-34)
    workchain = data[1]
    if workchain > 127:
        workchain = workchain - 256  # Convert to signed
    account_id = data[2:34].hex()
    return f"{workchain}:{account_id}"


# Telegram Gift collection addresses (user-friendly format)
TELEGRAM_GIFT_COLLECTIONS_UF = [
    "EQAGcE-2lLyGHa-lsaP7S1gJlhfG6qFJ6MmkLU-xejbEFvIo",  # Telegram Gifts
    "EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi",  # Star Gifts
    "EQCE80Aln8YfldnQLwWMvOfloLGgmPY0eGDJz9ufG3gRui3D",  # Loot Bags
]

# Convert to raw format for TonAPI SSE
TELEGRAM_GIFT_COLLECTIONS = [to_raw_address(addr) for addr in TELEGRAM_GIFT_COLLECTIONS_UF]


class GiftCollectorWorker:
    """
    Background worker that collects gift data from multiple sources.

    Runs continuously and populates the database with:
    - NFT transfer events (blockchain)
    - Public gift data (Telegram)
    - Wallet-username mappings
    """

    def __init__(self, db_session_factory):
        self.db = GiftHistoryService(db_session_factory)
        self.api_key = os.getenv("TONAPI_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Stats
        self.stats = {
            "nft_transfers_collected": 0,
            "wallets_linked": 0,
            "gifts_scanned": 0,
            "errors": 0,
            "started_at": None,
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def start(self):
        """Start the collector worker."""
        if self._running:
            logger.warning("Gift collector already running")
            return

        self._running = True
        self.stats["started_at"] = datetime.utcnow()

        logger.info("🚀 Starting Gift Collector Worker...")

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._nft_transfer_collector()),
            asyncio.create_task(self._metadata_enricher()),
            asyncio.create_task(self._stats_reporter()),
        ]

        logger.info("✅ Gift Collector Worker started with 3 background tasks")

    async def stop(self):
        """Stop the collector worker."""
        logger.info("Stopping Gift Collector Worker...")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close session
        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("✅ Gift Collector Worker stopped")

    async def _nft_transfer_collector(self):
        """
        Task 1: Collect NFT transfers from TON blockchain via SSE.

        Subscribes to all NFT transfer events and records them.
        This is the primary data source for tracking gift movements.
        """
        logger.info("📡 Starting NFT transfer collector (SSE)...")

        while self._running:
            try:
                await self._connect_sse()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"SSE connection error: {e}")
                if self._running:
                    logger.info("Reconnecting SSE in 10 seconds...")
                    await asyncio.sleep(10)

    async def _connect_sse(self):
        """Connect to TonAPI SSE and process events."""
        session = await self._get_session()

        # Subscribe to NFT transfers for gift collections
        url = f"{TONAPI_SSE_URL}/accounts/transactions"
        params = {
            "accounts": ",".join(TELEGRAM_GIFT_COLLECTIONS),
        }

        logger.info(f"Connecting to SSE stream for {len(TELEGRAM_GIFT_COLLECTIONS)} collections...")

        # Use aiohttp.ClientTimeout with total=None for infinite streaming
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=None)
        async with session.get(url, params=params, timeout=timeout) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error(f"SSE response body: {body[:500]}")
                raise Exception(f"SSE connection failed: {resp.status}")

            logger.info("✅ SSE connected, listening for NFT transfers...")

            async for line in resp.content:
                if not self._running:
                    break

                line = line.decode("utf-8").strip()

                # Skip empty lines and heartbeats
                if not line or line.startswith(":"):
                    continue

                # Parse SSE event
                if line.startswith("data: "):
                    try:
                        import json
                        data = json.loads(line[6:])
                        await self._process_sse_event(data)
                    except Exception as e:
                        logger.debug(f"Error processing SSE event: {e}")

    async def _process_sse_event(self, data: dict):
        """Process a single SSE event and store in database."""
        try:
            account_id = data.get("account_id", "")
            tx_hash = data.get("tx_hash", "")
            lt = data.get("lt", 0)

            # Fetch full event details
            session = await self._get_session()
            url = f"{TONAPI_BASE}/blockchain/transactions/{tx_hash}"

            async with session.get(url) as resp:
                if resp.status != 200:
                    return

                tx_data = await resp.json()

            # Parse the transaction for NFT transfer details
            in_msg = tx_data.get("in_msg", {})

            # Extract addresses
            source = in_msg.get("source", {}).get("address", "")
            dest = tx_data.get("account", {}).get("address", "")

            # Get NFT info from decoded body if available
            decoded = in_msg.get("decoded_body", {})
            nft_address = decoded.get("new_owner", dest)

            # Record the transfer
            recorded = await self.db.record_transfer(
                tx_hash=tx_hash,
                nft_address=account_id,  # The collection/NFT that triggered
                from_address=source,
                to_address=dest,
                block_timestamp=datetime.fromtimestamp(tx_data.get("utime", 0)),
                collection_address=account_id,
                is_telegram_gift=account_id in TELEGRAM_GIFT_COLLECTIONS
            )

            if recorded:
                self.stats["nft_transfers_collected"] += 1
                logger.debug(f"Recorded NFT transfer: {tx_hash[:16]}...")

        except Exception as e:
            logger.debug(f"Error processing event: {e}")

    async def _metadata_enricher(self):
        """
        Task 2: Enrich NFT records with metadata from Fragment.

        Periodically fetches metadata for NFTs to extract:
        - Sender username/ID
        - Recipient username/ID
        - Gift details

        This links wallets to Telegram users!
        """
        logger.info("🔍 Starting metadata enricher...")

        while self._running:
            try:
                await self._enrich_recent_nfts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Metadata enricher error: {e}")

            # Run every 5 minutes
            await asyncio.sleep(300)

    async def _enrich_recent_nfts(self):
        """Fetch and process metadata for recent NFT transfers."""
        session = await self._get_session()

        # Get recent NFT items from gift collections
        for collection in TELEGRAM_GIFT_COLLECTIONS:
            try:
                url = f"{TONAPI_BASE}/nfts/collections/{collection}/items"
                params = {"limit": 100}

                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue

                    data = await resp.json()
                    items = data.get("nft_items", [])

                for item in items:
                    await self._process_nft_metadata(item)

            except Exception as e:
                logger.debug(f"Error enriching collection {collection[:20]}: {e}")

    async def _process_nft_metadata(self, item: dict):
        """Process NFT item metadata to extract user connections."""
        try:
            nft_address = item.get("address", "")
            owner_address = item.get("owner", {}).get("address", "")
            metadata = item.get("metadata", {})

            # Get the slug from metadata or address
            name = metadata.get("name", "")

            # Try to extract slug for Fragment lookup
            # Format: "Gift Name – Collectible #12345" or similar
            slug = None
            if "–" in name:
                # Extract model and number
                parts = name.split("–")
                if len(parts) >= 2:
                    model_part = parts[0].strip().lower().replace(" ", "-")
                    number_part = parts[1].strip()
                    # Extract number
                    import re
                    match = re.search(r'#?(\d+)', number_part)
                    if match:
                        slug = f"{model_part}-{match.group(1)}"

            if not slug:
                return

            # Fetch full metadata from Fragment
            fragment_meta = await fragment_metadata.get_metadata(slug)
            if not fragment_meta:
                return

            # Extract sender/recipient info
            if fragment_meta.original_details:
                od = fragment_meta.original_details

                # Link sender wallet if we have sender info
                if od.sender_username and owner_address:
                    # The owner might be the recipient who upgraded to NFT
                    # We need to track the original sender's wallet through other means
                    pass

                # Link recipient wallet (current owner likely is or was recipient)
                if od.recipient_username:
                    await self.db.link_wallet_username(
                        wallet_address=owner_address,
                        username=od.recipient_username,
                        user_id=od.recipient_id,
                        source="fragment_nft"
                    )
                    self.stats["wallets_linked"] += 1
                    logger.info(f"Linked wallet {owner_address[:20]}... to @{od.recipient_username}")

                # Cache the gift metadata
                await self.db.cache_gift_metadata(
                    slug=slug,
                    name=fragment_meta.name,
                    model=fragment_meta.model,
                    backdrop=fragment_meta.backdrop,
                    symbol=fragment_meta.symbol,
                    sender_id=od.sender_id,
                    sender_username=od.sender_username,
                    recipient_id=od.recipient_id,
                    recipient_username=od.recipient_username,
                    image_url=fragment_meta.image_url,
                    transfer_date=od.transfer_date,
                    original_message=od.original_message
                )
                self.stats["gifts_scanned"] += 1

        except Exception as e:
            logger.debug(f"Error processing NFT metadata: {e}")

    async def _stats_reporter(self):
        """Task 3: Periodically report collection stats."""
        while self._running:
            await asyncio.sleep(600)  # Every 10 minutes

            if not self._running:
                break

            uptime = datetime.utcnow() - self.stats["started_at"] if self.stats["started_at"] else timedelta(0)

            logger.info(
                f"📊 Gift Collector Stats:\n"
                f"   Uptime: {uptime}\n"
                f"   NFT transfers: {self.stats['nft_transfers_collected']}\n"
                f"   Wallets linked: {self.stats['wallets_linked']}\n"
                f"   Gifts scanned: {self.stats['gifts_scanned']}\n"
                f"   Errors: {self.stats['errors']}"
            )


# Factory function
def create_gift_collector(db_session_factory) -> GiftCollectorWorker:
    """Create a gift collector worker instance."""
    return GiftCollectorWorker(db_session_factory)
