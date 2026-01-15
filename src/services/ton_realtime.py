"""TonAPI real-time NFT tracking service via SSE/WebSocket.

Uses TonAPI Streaming API to track NFT transfers in real-time.
Opcode 0x5fcc3d14 = NFT transfer (TEP-62 standard)
"""

import os
import json
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Awaitable
from decimal import Decimal

import aiohttp

logger = logging.getLogger(__name__)

# TonAPI endpoints
TONAPI_SSE_URL = "https://tonapi.io/v2/sse"
TONAPI_WEBHOOKS_URL = "https://rt.tonapi.io/webhooks"

# NFT Transfer opcode (TEP-62)
NFT_TRANSFER_OPCODE = "0x5fcc3d14"

# Telegram Gift collection addresses
TELEGRAM_GIFT_COLLECTIONS = {
    "EQCE80Aln8YfldnQLwWMvOfloLGgmPY0eGDJz9ufG3gRui3D",  # Loot Bags
    "EQAGcE-2lLyGHa-lsaP7S1gJlhfG6qFJ6MmkLU-xejbEFvIo",  # Telegram Gifts
    "EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi",  # Star Gifts
}


@dataclass
class NFTTransferEvent:
    """Real-time NFT transfer event."""
    nft_address: str
    from_address: str
    to_address: str
    timestamp: datetime
    tx_hash: str
    collection_address: Optional[str] = None
    collection_name: Optional[str] = None
    nft_name: Optional[str] = None
    price_ton: Optional[Decimal] = None  # If it was a sale
    is_telegram_gift: bool = False


# Type alias for event handler
EventHandler = Callable[[NFTTransferEvent], Awaitable[None]]


class TonRealtimeTracker:
    """Real-time NFT transfer tracker using TonAPI SSE."""

    def __init__(self):
        self.api_key = os.getenv("TONAPI_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._handlers: list[EventHandler] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Event buffer for database batch inserts
        self._event_buffer: list[NFTTransferEvent] = []
        self._buffer_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the session and stop tracking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._session and not self._session.closed:
            await self._session.close()

    def add_handler(self, handler: EventHandler):
        """Add event handler to be called on each NFT transfer."""
        self._handlers.append(handler)

    def remove_handler(self, handler: EventHandler):
        """Remove event handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def _notify_handlers(self, event: NFTTransferEvent):
        """Notify all handlers about an event."""
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Handler error: {e}")

    async def start_tracking(self, accounts: Optional[list[str]] = None):
        """
        Start tracking NFT transfers.

        Args:
            accounts: List of accounts to track. If None, tracks all Telegram gift collections.
        """
        if self._running:
            logger.warning("Tracker already running")
            return

        self._running = True

        # Default to Telegram gift collections
        if accounts is None:
            accounts = list(TELEGRAM_GIFT_COLLECTIONS)

        self._task = asyncio.create_task(self._sse_loop(accounts))
        logger.info(f"Started NFT tracking for {len(accounts)} accounts")

    async def stop_tracking(self):
        """Stop tracking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped NFT tracking")

    async def _sse_loop(self, accounts: list[str]):
        """Main SSE event loop."""
        while self._running:
            try:
                await self._connect_sse(accounts)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE connection error: {e}")
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def _connect_sse(self, accounts: list[str]):
        """Connect to SSE stream and process events."""
        session = await self._get_session()

        # Build SSE URL for account transactions with NFT transfer opcode filter
        url = f"{TONAPI_SSE_URL}/accounts/transactions"
        params = {
            "accounts": ",".join(accounts),
            "operations": NFT_TRANSFER_OPCODE
        }

        logger.info(f"Connecting to SSE: {url}")

        async with session.get(url, params=params, timeout=None) as resp:
            if resp.status != 200:
                raise Exception(f"SSE connection failed: {resp.status}")

            logger.info("SSE connected, waiting for events...")

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
                        data = json.loads(line[6:])
                        await self._process_event(data)
                    except json.JSONDecodeError:
                        logger.debug(f"Invalid JSON in SSE: {line}")
                    except Exception as e:
                        logger.error(f"Error processing SSE event: {e}")

    async def _process_event(self, data: dict):
        """Process a single SSE event."""
        try:
            account_id = data.get("account_id", "")
            tx_hash = data.get("tx_hash", "")
            lt = data.get("lt", 0)

            logger.debug(f"NFT event: account={account_id[:20]}..., tx={tx_hash[:20]}...")

            # Fetch full transaction details
            event = await self._fetch_event_details(account_id, tx_hash, lt)
            if event:
                # Add to buffer
                async with self._buffer_lock:
                    self._event_buffer.append(event)

                # Notify handlers
                await self._notify_handlers(event)

        except Exception as e:
            logger.error(f"Error processing event: {e}")

    async def _fetch_event_details(
        self,
        account_id: str,
        tx_hash: str,
        lt: int
    ) -> Optional[NFTTransferEvent]:
        """Fetch detailed event info from TonAPI."""
        try:
            session = await self._get_session()

            # Get NFT history for this account around this transaction
            url = f"https://tonapi.io/v2/accounts/{account_id}/nfts/history"
            params = {"limit": 1, "before_lt": lt + 1}

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                events = data.get("events", [])

                if not events:
                    return None

                event = events[0]
                actions = event.get("actions", [])

                for action in actions:
                    action_type = action.get("type", "")

                    if action_type == "NftItemTransfer":
                        transfer = action.get("NftItemTransfer", {})
                        nft = transfer.get("nft", {})

                        nft_address = nft.get("address", "")
                        collection = nft.get("collection", {})
                        collection_addr = collection.get("address", "")

                        return NFTTransferEvent(
                            nft_address=nft_address,
                            from_address=transfer.get("sender", {}).get("address", ""),
                            to_address=transfer.get("recipient", {}).get("address", ""),
                            timestamp=datetime.fromtimestamp(event.get("timestamp", 0)),
                            tx_hash=tx_hash,
                            collection_address=collection_addr,
                            collection_name=collection.get("name"),
                            nft_name=nft.get("metadata", {}).get("name"),
                            is_telegram_gift=collection_addr in TELEGRAM_GIFT_COLLECTIONS
                        )

                    elif action_type == "NftPurchase":
                        purchase = action.get("NftPurchase", {})
                        nft = purchase.get("nft", {})
                        amount = purchase.get("amount", {})

                        nft_address = nft.get("address", "")
                        collection = nft.get("collection", {})
                        collection_addr = collection.get("address", "")

                        price_nano = int(amount.get("value", 0))
                        price_ton = Decimal(str(price_nano)) / Decimal("1000000000")

                        return NFTTransferEvent(
                            nft_address=nft_address,
                            from_address=purchase.get("seller", {}).get("address", ""),
                            to_address=purchase.get("buyer", {}).get("address", ""),
                            timestamp=datetime.fromtimestamp(event.get("timestamp", 0)),
                            tx_hash=tx_hash,
                            collection_address=collection_addr,
                            collection_name=collection.get("name"),
                            nft_name=nft.get("metadata", {}).get("name"),
                            price_ton=price_ton,
                            is_telegram_gift=collection_addr in TELEGRAM_GIFT_COLLECTIONS
                        )

        except Exception as e:
            logger.error(f"Error fetching event details: {e}")

        return None

    async def get_buffered_events(self, clear: bool = True) -> list[NFTTransferEvent]:
        """
        Get buffered events for batch processing.

        Args:
            clear: Whether to clear the buffer after getting events

        Returns:
            List of buffered events
        """
        async with self._buffer_lock:
            events = list(self._event_buffer)
            if clear:
                self._event_buffer.clear()
            return events

    async def track_specific_wallet(
        self,
        wallet_address: str,
        handler: EventHandler,
        duration_seconds: int = 3600
    ):
        """
        Track NFT transfers for a specific wallet for a limited time.

        Args:
            wallet_address: Wallet to track
            handler: Callback for events
            duration_seconds: How long to track (default 1 hour)
        """
        self.add_handler(handler)

        try:
            # Start tracking with this wallet added
            current_accounts = list(TELEGRAM_GIFT_COLLECTIONS)
            current_accounts.append(wallet_address)

            # This would need a separate tracker instance in production
            # For now, just log the intent
            logger.info(f"Would track wallet {wallet_address} for {duration_seconds}s")

        finally:
            self.remove_handler(handler)


# Global instance
ton_realtime = TonRealtimeTracker()


# Example handler for logging
async def log_nft_transfer(event: NFTTransferEvent):
    """Example handler that logs NFT transfers."""
    gift_tag = " [TG GIFT]" if event.is_telegram_gift else ""
    price_info = f" for {event.price_ton} TON" if event.price_ton else ""

    logger.info(
        f"NFT Transfer{gift_tag}: {event.nft_name or 'Unknown'}"
        f" from {event.from_address[:10]}..."
        f" to {event.to_address[:10]}..."
        f"{price_info}"
    )
