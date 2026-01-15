"""Fragment NFT metadata parser service.

Fetches and parses metadata for Telegram gift NFTs from Fragment.
URL pattern: https://nft.fragment.com/gift/[giftname]-[id].json
"""

import logging
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

# Fragment NFT metadata base URL
FRAGMENT_NFT_BASE = "https://nft.fragment.com/gift"


@dataclass
class GiftAttribute:
    """Single attribute/trait of a gift NFT."""
    trait_type: str
    value: str
    rarity_pct: Optional[float] = None  # Percentage of NFTs with this trait


@dataclass
class GiftOriginalDetails:
    """Original gift transfer details preserved in NFT."""
    sender_id: Optional[int] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    recipient_id: Optional[int] = None
    recipient_username: Optional[str] = None
    recipient_name: Optional[str] = None
    transfer_date: Optional[datetime] = None
    original_message: Optional[str] = None


@dataclass
class FragmentGiftMetadata:
    """Complete metadata for a Telegram gift NFT from Fragment."""
    # Basic info
    slug: str  # e.g., "gem-signet-5475"
    name: str  # e.g., "Gem Signet – Collectible #5475"
    description: Optional[str] = None

    # Visual assets
    image_url: Optional[str] = None
    animation_url: Optional[str] = None  # Lottie JSON
    lottie_url: Optional[str] = None

    # Attributes/traits
    attributes: list[GiftAttribute] = field(default_factory=list)

    # Model, backdrop, symbol (extracted from attributes)
    model: Optional[str] = None
    backdrop: Optional[str] = None
    symbol: Optional[str] = None

    # Original gift details (sender/recipient)
    original_details: Optional[GiftOriginalDetails] = None

    # External links
    external_url: Optional[str] = None  # t.me/nft/...
    fragment_url: Optional[str] = None

    # Collection info
    collection_name: Optional[str] = None
    collection_address: Optional[str] = None

    # Raw JSON for debugging
    raw_json: Optional[dict] = None

    @property
    def model_rarity(self) -> Optional[float]:
        """Get model trait rarity percentage."""
        for attr in self.attributes:
            if attr.trait_type.lower() == "model":
                return attr.rarity_pct
        return None

    @property
    def backdrop_rarity(self) -> Optional[float]:
        """Get backdrop trait rarity percentage."""
        for attr in self.attributes:
            if attr.trait_type.lower() == "backdrop":
                return attr.rarity_pct
        return None


class FragmentMetadataService:
    """Service for fetching NFT metadata from Fragment."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: dict[str, tuple[FragmentGiftMetadata, float]] = {}
        self._cache_ttl = 3600  # 1 hour cache

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_metadata(self, slug: str) -> Optional[FragmentGiftMetadata]:
        """
        Fetch metadata for a gift NFT from Fragment.

        Args:
            slug: Gift slug (e.g., "gem-signet-5475" or "icecream-172405")

        Returns:
            FragmentGiftMetadata or None if not found
        """
        import time

        # Check cache
        if slug in self._cache:
            metadata, timestamp = self._cache[slug]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Fragment metadata cache hit for {slug}")
                return metadata

        try:
            session = await self._get_session()

            # Fetch JSON metadata
            url = f"{FRAGMENT_NFT_BASE}/{slug}.json"
            logger.info(f"Fetching Fragment metadata: {url}")

            async with session.get(url, timeout=10) as resp:
                if resp.status == 404:
                    logger.debug(f"Fragment metadata not found for {slug}")
                    return None

                if resp.status != 200:
                    logger.warning(f"Fragment API error {resp.status} for {slug}")
                    return None

                data = await resp.json()

            # Parse metadata
            metadata = self._parse_metadata(slug, data)

            # Cache result
            self._cache[slug] = (metadata, time.time())

            logger.info(f"Fragment metadata for {slug}: model={metadata.model}, backdrop={metadata.backdrop}")

            return metadata

        except Exception as e:
            logger.error(f"Failed to fetch Fragment metadata for {slug}: {e}")
            return None

    def _parse_metadata(self, slug: str, data: dict) -> FragmentGiftMetadata:
        """Parse raw JSON into FragmentGiftMetadata."""

        # Parse attributes
        attributes = []
        model = None
        backdrop = None
        symbol = None

        for attr in data.get("attributes", []):
            trait_type = attr.get("trait_type", "")
            value = attr.get("value", "")
            rarity = attr.get("percentage") or attr.get("rarity_percentage")

            if rarity:
                try:
                    rarity = float(rarity)
                except (ValueError, TypeError):
                    rarity = None

            attributes.append(GiftAttribute(
                trait_type=trait_type,
                value=value,
                rarity_pct=rarity
            ))

            # Extract key traits
            trait_lower = trait_type.lower()
            if trait_lower == "model":
                model = value
            elif trait_lower == "backdrop":
                backdrop = value
            elif trait_lower == "symbol":
                symbol = value

        # Parse original details if present
        original_details = None
        original_data = data.get("original_details") or data.get("starGiftAttributeOriginalDetails")
        if original_data:
            original_details = GiftOriginalDetails(
                sender_id=original_data.get("sender_id"),
                sender_username=original_data.get("sender_username"),
                sender_name=original_data.get("sender_name"),
                recipient_id=original_data.get("recipient_id"),
                recipient_username=original_data.get("recipient_username"),
                recipient_name=original_data.get("recipient_name"),
                original_message=original_data.get("message")
            )

            # Parse date
            date_str = original_data.get("date") or original_data.get("transfer_date")
            if date_str:
                try:
                    if isinstance(date_str, int):
                        original_details.transfer_date = datetime.fromtimestamp(date_str)
                    else:
                        original_details.transfer_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:
                    pass

        return FragmentGiftMetadata(
            slug=slug,
            name=data.get("name", slug),
            description=data.get("description"),
            image_url=data.get("image"),
            animation_url=data.get("animation_url"),
            lottie_url=f"{FRAGMENT_NFT_BASE}/{slug}.lottie.json",
            attributes=attributes,
            model=model,
            backdrop=backdrop,
            symbol=symbol,
            original_details=original_details,
            external_url=data.get("external_url") or f"https://t.me/nft/{slug}",
            fragment_url=f"https://fragment.com/gift/{slug}",
            raw_json=data
        )

    async def get_sender_recipient(self, slug: str) -> tuple[Optional[dict], Optional[dict]]:
        """
        Get sender and recipient info from gift metadata.

        Returns:
            Tuple of (sender_info, recipient_info) dicts or (None, None)
        """
        metadata = await self.get_metadata(slug)
        if not metadata or not metadata.original_details:
            return None, None

        od = metadata.original_details

        sender = None
        if od.sender_id or od.sender_username:
            sender = {
                "user_id": od.sender_id,
                "username": od.sender_username,
                "name": od.sender_name
            }

        recipient = None
        if od.recipient_id or od.recipient_username:
            recipient = {
                "user_id": od.recipient_id,
                "username": od.recipient_username,
                "name": od.recipient_name
            }

        return sender, recipient

    async def get_gift_traits(self, slug: str) -> dict:
        """
        Get gift traits (model, backdrop, symbol) with rarities.

        Returns:
            Dict with trait info
        """
        metadata = await self.get_metadata(slug)
        if not metadata:
            return {}

        return {
            "model": {
                "value": metadata.model,
                "rarity_pct": metadata.model_rarity
            },
            "backdrop": {
                "value": metadata.backdrop,
                "rarity_pct": metadata.backdrop_rarity
            },
            "symbol": {
                "value": metadata.symbol,
                "rarity_pct": None  # Usually not provided
            },
            "all_attributes": [
                {
                    "trait_type": a.trait_type,
                    "value": a.value,
                    "rarity_pct": a.rarity_pct
                }
                for a in metadata.attributes
            ]
        }


# Global instance
fragment_metadata = FragmentMetadataService()
