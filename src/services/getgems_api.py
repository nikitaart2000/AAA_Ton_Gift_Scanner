"""GetGems GraphQL API service for NFT marketplace data.

GetGems is the largest NFT marketplace on TON blockchain.
GraphQL endpoint: https://api.getgems.io/graphql
"""

import logging
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

GETGEMS_GRAPHQL_URL = "https://api.getgems.io/graphql"

# Known Telegram Gifts collection addresses
TELEGRAM_GIFT_COLLECTIONS = {
    "EQCE80Aln8YfldnQLwWMvOfloLGgmPY0eGDJz9ufG3gRui3D": "Loot Bags",
    "EQAGcE-2lLyGHa-lsaP7S1gJlhfG6qFJ6MmkLU-xejbEFvIo": "Telegram Gifts",
    "EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi": "Telegram Star Gifts",
}


@dataclass
class GetGemsNFT:
    """NFT item from GetGems."""
    address: str
    name: str
    collection_address: Optional[str] = None
    collection_name: Optional[str] = None
    owner_address: Optional[str] = None
    image_url: Optional[str] = None
    sale_price: Optional[Decimal] = None  # Current listing price in TON
    last_sale_price: Optional[Decimal] = None  # Last sold price in TON
    last_sale_date: Optional[datetime] = None
    metadata: Optional[dict] = None


@dataclass
class GetGemsCollection:
    """NFT collection from GetGems."""
    address: str
    name: str
    items_count: int = 0
    owners_count: int = 0
    floor_price: Optional[Decimal] = None  # In TON
    volume_24h: Optional[Decimal] = None
    volume_total: Optional[Decimal] = None
    cover_url: Optional[str] = None


@dataclass
class GetGemsSale:
    """NFT sale event from GetGems."""
    nft_address: str
    nft_name: str
    collection_name: Optional[str] = None
    price: Decimal  # In TON
    buyer_address: str
    seller_address: str
    timestamp: datetime


class GetGemsService:
    """Service for interacting with GetGems GraphQL API."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, tuple[any, float]] = {}
        self._cache_ttl = 60  # 1 minute cache for price data

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _graphql_query(self, query: str, variables: Optional[dict] = None) -> Optional[dict]:
        """Execute GraphQL query."""
        try:
            session = await self._get_session()

            payload = {"query": query}
            if variables:
                payload["variables"] = variables

            async with session.post(
                GETGEMS_GRAPHQL_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"GetGems API error: {resp.status}")
                    return None

                data = await resp.json()

                if "errors" in data:
                    logger.warning(f"GetGems GraphQL errors: {data['errors']}")
                    return None

                return data.get("data")

        except Exception as e:
            logger.error(f"GetGems GraphQL query failed: {e}")
            return None

    async def get_collection_info(self, collection_address: str) -> Optional[GetGemsCollection]:
        """
        Get collection information.

        Args:
            collection_address: TON address of the collection

        Returns:
            GetGemsCollection or None
        """
        query = """
        query GetCollection($address: String!) {
            nftCollectionByAddress(address: $address) {
                address
                name
                approximateItemsCount
                approximateHoldersCount
                floorPriceNano
                cover {
                    image {
                        originalUrl
                    }
                }
            }
        }
        """

        data = await self._graphql_query(query, {"address": collection_address})
        if not data or not data.get("nftCollectionByAddress"):
            return None

        col = data["nftCollectionByAddress"]

        floor_price = None
        if col.get("floorPriceNano"):
            floor_price = Decimal(str(int(col["floorPriceNano"]))) / Decimal("1000000000")

        cover_url = None
        if col.get("cover", {}).get("image", {}).get("originalUrl"):
            cover_url = col["cover"]["image"]["originalUrl"]

        return GetGemsCollection(
            address=col["address"],
            name=col.get("name", "Unknown"),
            items_count=col.get("approximateItemsCount", 0),
            owners_count=col.get("approximateHoldersCount", 0),
            floor_price=floor_price,
            cover_url=cover_url
        )

    async def get_nft_info(self, nft_address: str) -> Optional[GetGemsNFT]:
        """
        Get NFT item information.

        Args:
            nft_address: TON address of the NFT

        Returns:
            GetGemsNFT or None
        """
        query = """
        query GetNFT($address: String!) {
            nftItemByAddress(address: $address) {
                address
                name
                owner {
                    address
                }
                collection {
                    address
                    name
                }
                content {
                    image {
                        originalUrl
                    }
                }
                sale {
                    fullPrice
                }
            }
        }
        """

        data = await self._graphql_query(query, {"address": nft_address})
        if not data or not data.get("nftItemByAddress"):
            return None

        nft = data["nftItemByAddress"]

        sale_price = None
        if nft.get("sale", {}).get("fullPrice"):
            sale_price = Decimal(str(nft["sale"]["fullPrice"])) / Decimal("1000000000")

        image_url = None
        if nft.get("content", {}).get("image", {}).get("originalUrl"):
            image_url = nft["content"]["image"]["originalUrl"]

        return GetGemsNFT(
            address=nft["address"],
            name=nft.get("name", "Unknown"),
            collection_address=nft.get("collection", {}).get("address"),
            collection_name=nft.get("collection", {}).get("name"),
            owner_address=nft.get("owner", {}).get("address"),
            image_url=image_url,
            sale_price=sale_price
        )

    async def get_collection_items(
        self,
        collection_address: str,
        limit: int = 50,
        offset: int = 0,
        on_sale_only: bool = False
    ) -> list[GetGemsNFT]:
        """
        Get items from a collection.

        Args:
            collection_address: TON address of the collection
            limit: Max items to return
            offset: Pagination offset
            on_sale_only: Only return items currently for sale

        Returns:
            List of GetGemsNFT
        """
        query = """
        query GetCollectionItems($address: String!, $first: Int!, $skip: Int!, $onSale: Boolean) {
            nftItemsByCollection(
                collectionAddress: $address
                first: $first
                skip: $skip
                filter: { sale: $onSale }
            ) {
                items {
                    address
                    name
                    owner {
                        address
                    }
                    content {
                        image {
                            originalUrl
                        }
                    }
                    sale {
                        fullPrice
                    }
                }
            }
        }
        """

        variables = {
            "address": collection_address,
            "first": limit,
            "skip": offset,
            "onSale": on_sale_only if on_sale_only else None
        }

        data = await self._graphql_query(query, variables)
        if not data or not data.get("nftItemsByCollection"):
            return []

        items = data["nftItemsByCollection"].get("items", [])
        results = []

        for nft in items:
            sale_price = None
            if nft.get("sale", {}).get("fullPrice"):
                sale_price = Decimal(str(nft["sale"]["fullPrice"])) / Decimal("1000000000")

            image_url = None
            if nft.get("content", {}).get("image", {}).get("originalUrl"):
                image_url = nft["content"]["image"]["originalUrl"]

            results.append(GetGemsNFT(
                address=nft["address"],
                name=nft.get("name", "Unknown"),
                collection_address=collection_address,
                owner_address=nft.get("owner", {}).get("address"),
                image_url=image_url,
                sale_price=sale_price
            ))

        return results

    async def get_user_nfts(self, wallet_address: str, limit: int = 100) -> list[GetGemsNFT]:
        """
        Get NFTs owned by a wallet.

        Args:
            wallet_address: TON wallet address
            limit: Max items to return

        Returns:
            List of GetGemsNFT
        """
        query = """
        query GetUserNFTs($address: String!, $first: Int!) {
            nftItemsByOwner(ownerAddress: $address, first: $first) {
                items {
                    address
                    name
                    collection {
                        address
                        name
                    }
                    content {
                        image {
                            originalUrl
                        }
                    }
                    sale {
                        fullPrice
                    }
                }
            }
        }
        """

        data = await self._graphql_query(query, {"address": wallet_address, "first": limit})
        if not data or not data.get("nftItemsByOwner"):
            return []

        items = data["nftItemsByOwner"].get("items", [])
        results = []

        for nft in items:
            sale_price = None
            if nft.get("sale", {}).get("fullPrice"):
                sale_price = Decimal(str(nft["sale"]["fullPrice"])) / Decimal("1000000000")

            image_url = None
            if nft.get("content", {}).get("image", {}).get("originalUrl"):
                image_url = nft["content"]["image"]["originalUrl"]

            results.append(GetGemsNFT(
                address=nft["address"],
                name=nft.get("name", "Unknown"),
                collection_address=nft.get("collection", {}).get("address"),
                collection_name=nft.get("collection", {}).get("name"),
                owner_address=wallet_address,
                image_url=image_url,
                sale_price=sale_price
            ))

        return results

    async def search_telegram_gifts(self, query_str: str = "", limit: int = 50) -> list[GetGemsNFT]:
        """
        Search for Telegram gift NFTs.

        Args:
            query_str: Search query
            limit: Max items to return

        Returns:
            List of GetGemsNFT matching Telegram gift collections
        """
        all_gifts = []

        for collection_address, collection_name in TELEGRAM_GIFT_COLLECTIONS.items():
            try:
                items = await self.get_collection_items(
                    collection_address,
                    limit=limit,
                    on_sale_only=True
                )

                for item in items:
                    item.collection_name = collection_name
                    if query_str.lower() in item.name.lower():
                        all_gifts.append(item)
                    elif not query_str:
                        all_gifts.append(item)

            except Exception as e:
                logger.warning(f"Failed to get items from {collection_name}: {e}")
                continue

        # Sort by price
        all_gifts.sort(key=lambda x: x.sale_price or Decimal("999999"))

        return all_gifts[:limit]

    async def get_telegram_gifts_floor(self) -> dict[str, Optional[Decimal]]:
        """
        Get floor prices for all Telegram gift collections.

        Returns:
            Dict mapping collection name to floor price in TON
        """
        floors = {}

        for collection_address, collection_name in TELEGRAM_GIFT_COLLECTIONS.items():
            try:
                info = await self.get_collection_info(collection_address)
                if info:
                    floors[collection_name] = info.floor_price
                else:
                    floors[collection_name] = None
            except Exception as e:
                logger.warning(f"Failed to get floor for {collection_name}: {e}")
                floors[collection_name] = None

        return floors


# Global instance
getgems_api = GetGemsService()
