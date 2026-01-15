"""TON blockchain API service for NFT gift data."""

import os
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

# Known Telegram Gift NFT collections on TON
GIFT_COLLECTIONS = {
    # Основные коллекции подарков Telegram
    "EQAGcE-2lLyGHa-lsaP7S1gJlhfG6qFJ6MmkLU-xejbEFvIo": "Telegram Gifts",
    "EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi": "Telegram Star Gifts",
}


@dataclass
class NFTGift:
    """NFT gift information from TON blockchain."""
    address: str
    name: str
    collection: str
    image_url: Optional[str] = None
    owner_address: Optional[str] = None
    metadata: Optional[dict] = None
    last_sale_price: Optional[float] = None  # В TON
    last_sale_date: Optional[datetime] = None


@dataclass
class WalletInfo:
    """TON wallet information."""
    address: str
    balance: float  # В TON
    nft_count: int
    gift_nfts: list[NFTGift]


class TonAPIService:
    """Service for interacting with TON blockchain via tonapi.io."""

    def __init__(self):
        self.api_key = os.getenv("TONAPI_KEY", "")
        self.base_url = "https://tonapi.io/v2"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def resolve_domain(self, domain: str) -> Optional[str]:
        """
        Resolve TON DNS domain to wallet address.

        Args:
            domain: TON DNS domain (e.g., "username.t.me" or "wallet.ton")

        Returns:
            Wallet address or None
        """
        try:
            session = await self._get_session()

            # Убираем @ если есть
            domain = domain.lstrip("@")

            # Пробуем t.me домен (Telegram username -> TON address)
            url = f"{self.base_url}/dns/{domain}.t.me/resolve"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    wallet = data.get("wallet", {})
                    address = wallet.get("address")
                    if address:
                        logger.info(f"Resolved {domain}.t.me -> {address}")
                        return address

            # Пробуем .ton домен
            url = f"{self.base_url}/dns/{domain}.ton/resolve"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    wallet = data.get("wallet", {})
                    address = wallet.get("address")
                    if address:
                        logger.info(f"Resolved {domain}.ton -> {address}")
                        return address

            logger.debug(f"Could not resolve domain: {domain}")
            return None

        except Exception as e:
            logger.warning(f"Failed to resolve domain {domain}: {e}")
            return None

    async def get_wallet_nfts(self, address: str) -> list[NFTGift]:
        """
        Get NFT gifts owned by wallet.

        Args:
            address: TON wallet address

        Returns:
            List of NFT gifts
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/accounts/{address}/nfts"

            params = {
                "limit": 1000,
                "indirect_ownership": "true"
            }

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to get NFTs for {address}: {resp.status}")
                    return []

                data = await resp.json()
                nfts = data.get("nft_items", [])

                gifts = []
                for nft in nfts:
                    gift = self._parse_nft_gift(nft)
                    if gift:
                        gifts.append(gift)

                logger.info(f"Found {len(gifts)} gift NFTs for {address}")
                return gifts

        except Exception as e:
            logger.error(f"Failed to get wallet NFTs: {e}", exc_info=True)
            return []

    def _parse_nft_gift(self, nft: dict) -> Optional[NFTGift]:
        """Parse NFT data and check if it's a gift."""
        try:
            collection = nft.get("collection", {})
            collection_address = collection.get("address", "")

            # Проверяем, является ли это коллекцией подарков
            is_gift_collection = collection_address in GIFT_COLLECTIONS

            # Также проверяем по имени коллекции
            collection_name = collection.get("name", "")
            is_gift_by_name = any(
                keyword in collection_name.lower()
                for keyword in ["gift", "подарок", "telegram"]
            )

            if not is_gift_collection and not is_gift_by_name:
                return None

            metadata = nft.get("metadata", {})

            # Получаем информацию о последней продаже
            sale = nft.get("sale", {})
            last_sale_price = None
            if sale:
                price = sale.get("price", {})
                # Цена в нанотонах
                value = price.get("value", 0)
                if value:
                    last_sale_price = int(value) / 1e9  # Конвертируем в TON

            return NFTGift(
                address=nft.get("address", ""),
                name=metadata.get("name", "Unknown Gift"),
                collection=collection_name or GIFT_COLLECTIONS.get(collection_address, "Unknown"),
                image_url=metadata.get("image"),
                owner_address=nft.get("owner", {}).get("address"),
                metadata=metadata,
                last_sale_price=last_sale_price
            )

        except Exception as e:
            logger.warning(f"Failed to parse NFT: {e}")
            return None

    async def get_wallet_info(self, address: str) -> Optional[WalletInfo]:
        """
        Get full wallet information including balance and NFTs.

        Args:
            address: TON wallet address

        Returns:
            WalletInfo or None
        """
        try:
            session = await self._get_session()

            # Получаем баланс
            url = f"{self.base_url}/accounts/{address}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to get wallet info for {address}: {resp.status}")
                    return None

                data = await resp.json()

            # Баланс в нанотонах
            balance_nano = int(data.get("balance", 0))
            balance = balance_nano / 1e9

            # Получаем NFT подарки
            gifts = await self.get_wallet_nfts(address)

            return WalletInfo(
                address=address,
                balance=balance,
                nft_count=len(gifts),
                gift_nfts=gifts
            )

        except Exception as e:
            logger.error(f"Failed to get wallet info: {e}", exc_info=True)
            return None

    async def get_nft_history(self, nft_address: str) -> list[dict]:
        """
        Get transaction history for an NFT.

        Args:
            nft_address: NFT address

        Returns:
            List of transactions
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/nfts/{nft_address}/history"

            async with session.get(url) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                return data.get("events", [])

        except Exception as e:
            logger.warning(f"Failed to get NFT history: {e}")
            return []

    async def get_account_nft_history(self, address: str, limit: int = 100) -> list[dict]:
        """
        Get NFT transfer history for an account.

        This shows all NFT sends and receives - who sent what to whom.

        Args:
            address: TON wallet address
            limit: Max number of events (1-1000)

        Returns:
            List of NFT events (transfers, purchases, etc.)
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/accounts/{address}/nfts/history"

            params = {"limit": min(limit, 1000)}

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to get NFT history for {address}: {resp.status}")
                    return []

                data = await resp.json()
                events = data.get("events", [])
                logger.info(f"Got {len(events)} NFT events for {address}")
                return events

        except Exception as e:
            logger.warning(f"Failed to get account NFT history: {e}")
            return []

    def parse_nft_events(self, events: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Parse NFT events into sent and received gifts.

        Args:
            events: Raw events from TonAPI

        Returns:
            Tuple of (received_gifts, sent_gifts)
        """
        received = []
        sent = []

        for event in events:
            try:
                actions = event.get("actions", [])
                timestamp = event.get("timestamp", 0)

                for action in actions:
                    action_type = action.get("type", "")

                    # NFT Transfer
                    if action_type == "NftItemTransfer":
                        transfer = action.get("NftItemTransfer", {})
                        nft = transfer.get("nft", {})
                        sender = transfer.get("sender", {}).get("address", "")
                        recipient = transfer.get("recipient", {}).get("address", "")

                        gift_data = {
                            "nft_address": nft.get("address", ""),
                            "name": nft.get("metadata", {}).get("name", "Unknown"),
                            "collection": nft.get("collection", {}).get("name", ""),
                            "sender": sender,
                            "recipient": recipient,
                            "timestamp": timestamp,
                            "action": "transfer"
                        }

                        # Определяем направление по контексту события
                        received.append(gift_data)

                    # NFT Purchase
                    elif action_type == "NftPurchase":
                        purchase = action.get("NftPurchase", {})
                        nft = purchase.get("nft", {})
                        buyer = purchase.get("buyer", {}).get("address", "")
                        seller = purchase.get("seller", {}).get("address", "")
                        amount = purchase.get("amount", {})

                        # Цена в нанотонах
                        price_nano = int(amount.get("value", 0))
                        price_ton = price_nano / 1e9

                        gift_data = {
                            "nft_address": nft.get("address", ""),
                            "name": nft.get("metadata", {}).get("name", "Unknown"),
                            "collection": nft.get("collection", {}).get("name", ""),
                            "buyer": buyer,
                            "seller": seller,
                            "price_ton": price_ton,
                            "timestamp": timestamp,
                            "action": "purchase"
                        }

                        received.append(gift_data)

            except Exception as e:
                logger.debug(f"Failed to parse event: {e}")
                continue

        return received, sent


# Global instance
ton_api = TonAPIService()
