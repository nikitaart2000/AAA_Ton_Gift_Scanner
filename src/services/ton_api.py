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


# Global instance
ton_api = TonAPIService()
