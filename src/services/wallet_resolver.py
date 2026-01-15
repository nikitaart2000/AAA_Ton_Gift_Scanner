"""Wallet resolver service - finds TON wallet by Telegram user through multiple sources.

Sources:
1. TON DNS (username.t.me -> wallet)
2. Tonnel API (marketplace connections)
3. Fragment NFT metadata (gift upgrade history)
4. Our database (previously discovered connections)
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

# Tonnel relayer addresses (used to detect trades)
TONNEL_RELAYER = "EQDvzep8LkSIaHTv4q15y0dKQbkRYlbTXRWMjS5c4JJD3Sch"

# Known marketplace wallet patterns
MARKETPLACE_WALLETS = {
    "tonnel": ["EQDvzep8LkSIaHTv4q15y0dKQbkRYlbTXRWMjS5c4JJD3Sch"],
    "getgems": ["EQBYTuYbLf8INxFtD8tQeNk5ZLy-nAX9ahQbG_yl1qQ-GEMS"],
    "fragment": [],
}


@dataclass
class WalletMatch:
    """A discovered wallet-username connection."""
    wallet_address: str
    source: str  # "ton_dns", "tonnel", "fragment", "database"
    confidence: str  # "high", "medium", "low"
    extra_info: Optional[str] = None


class WalletResolverService:
    """Service to find TON wallet by Telegram username/user_id through multiple sources."""

    def __init__(self):
        self.tonapi_key = os.getenv("TONAPI_KEY", "")
        self.tonapi_base = "https://tonapi.io/v2"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.tonapi_key:
                headers["Authorization"] = f"Bearer {self.tonapi_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def resolve(
        self,
        username: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> list[WalletMatch]:
        """
        Find all wallet addresses associated with a Telegram user.

        Args:
            username: Telegram username (without @)
            user_id: Telegram user ID

        Returns:
            List of WalletMatch objects, sorted by confidence
        """
        matches: list[WalletMatch] = []

        if username:
            username = username.lstrip("@").lower()

        # 1. Try TON DNS resolution
        if username:
            dns_wallet = await self._resolve_ton_dns(username)
            if dns_wallet:
                matches.append(WalletMatch(
                    wallet_address=dns_wallet,
                    source="ton_dns",
                    confidence="high",
                    extra_info=f"{username}.t.me"
                ))

        # 2. Search through Tonnel trades
        if username or user_id:
            tonnel_matches = await self._search_tonnel(username, user_id)
            matches.extend(tonnel_matches)

        # 3. Search through Fragment NFT metadata
        if username or user_id:
            fragment_matches = await self._search_fragment_nfts(username, user_id)
            matches.extend(fragment_matches)

        # Sort by confidence
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        matches.sort(key=lambda m: confidence_order.get(m.confidence, 3))

        # Deduplicate by wallet address
        seen = set()
        unique_matches = []
        for m in matches:
            if m.wallet_address not in seen:
                seen.add(m.wallet_address)
                unique_matches.append(m)

        return unique_matches

    async def _resolve_ton_dns(self, username: str) -> Optional[str]:
        """Resolve username via TON DNS."""
        try:
            session = await self._get_session()

            # Try .t.me domain first
            url = f"{self.tonapi_base}/dns/{username}.t.me/resolve"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    wallet = data.get("wallet", {})
                    address = wallet.get("address")
                    if address:
                        logger.info(f"TON DNS: {username}.t.me -> {address}")
                        return address

            # Try .ton domain
            url = f"{self.tonapi_base}/dns/{username}.ton/resolve"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    wallet = data.get("wallet", {})
                    address = wallet.get("address")
                    if address:
                        logger.info(f"TON DNS: {username}.ton -> {address}")
                        return address

        except Exception as e:
            logger.warning(f"TON DNS resolution failed: {e}")

        return None

    async def _search_tonnel(
        self,
        username: Optional[str],
        user_id: Optional[int]
    ) -> list[WalletMatch]:
        """
        Search for wallet connections through Tonnel marketplace.

        Tonnel exposes trade data that can link usernames to wallets.
        """
        matches = []

        try:
            session = await self._get_session()

            # Search Tonnel relayer transactions for this username
            # Tonnel uses a specific format where username is encoded in transaction
            url = f"{self.tonapi_base}/accounts/{TONNEL_RELAYER}/events"
            params = {"limit": 100}

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return matches

                data = await resp.json()
                events = data.get("events", [])

                for event in events:
                    # Look for NftItemTransfer or TonTransfer with comment
                    actions = event.get("actions", [])
                    for action in actions:
                        # Check if there's a connection to our user
                        comment = action.get("TonTransfer", {}).get("comment", "")

                        if username and username.lower() in comment.lower():
                            # Found potential match - extract sender/recipient wallet
                            sender = action.get("TonTransfer", {}).get("sender", {}).get("address")
                            recipient = action.get("TonTransfer", {}).get("recipient", {}).get("address")

                            # The user's wallet is likely the non-relayer one
                            user_wallet = sender if recipient == TONNEL_RELAYER else recipient

                            if user_wallet and user_wallet != TONNEL_RELAYER:
                                matches.append(WalletMatch(
                                    wallet_address=user_wallet,
                                    source="tonnel",
                                    confidence="medium",
                                    extra_info=comment[:50]
                                ))

        except Exception as e:
            logger.warning(f"Tonnel search failed: {e}")

        return matches

    async def _search_fragment_nfts(
        self,
        username: Optional[str],
        user_id: Optional[int]
    ) -> list[WalletMatch]:
        """
        Search Fragment NFT metadata for wallet connections.

        When a gift is upgraded to NFT, the metadata contains sender/recipient info.
        If we find an NFT where this user is sender/recipient, we can find their wallet.
        """
        matches = []

        try:
            # Import fragment service
            from src.services.fragment_metadata import fragment_metadata

            # This would require searching through NFT collections
            # For now, we can search through known gift NFTs
            # In a full implementation, this would query our database of collected metadata

            # Example: search TonAPI for NFTs with this user in metadata
            session = await self._get_session()

            # Search in Telegram Gift collections
            gift_collections = [
                "EQAGcE-2lLyGHa-lsaP7S1gJlhfG6qFJ6MmkLU-xejbEFvIo",  # Telegram Gifts
                "EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi",  # Star Gifts
            ]

            for collection in gift_collections:
                # Get recent NFT items from collection
                url = f"{self.tonapi_base}/nfts/collections/{collection}/items"
                params = {"limit": 50}

                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        continue

                    data = await resp.json()
                    items = data.get("nft_items", [])

                    for item in items:
                        metadata = item.get("metadata", {})
                        attrs = metadata.get("attributes", [])

                        # Look for sender/recipient in attributes
                        for attr in attrs:
                            trait = attr.get("trait_type", "").lower()
                            value = str(attr.get("value", "")).lower()

                            # Check if username matches
                            if username and username.lower() in value:
                                owner = item.get("owner", {}).get("address")
                                if owner:
                                    matches.append(WalletMatch(
                                        wallet_address=owner,
                                        source="fragment",
                                        confidence="medium",
                                        extra_info=f"NFT owner: {metadata.get('name', 'unknown')}"
                                    ))

        except Exception as e:
            logger.warning(f"Fragment NFT search failed: {e}")

        return matches

    async def get_best_wallet(
        self,
        username: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Get the most likely wallet address for a user.

        Returns:
            Best matching wallet address or None
        """
        matches = await self.resolve(username, user_id)
        return matches[0].wallet_address if matches else None


# Global instance
wallet_resolver = WalletResolverService()
