"""Core data models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """Market event types."""

    BUY = "buy"
    LISTING = "listing"
    CHANGE_PRICE = "change_price"


class EventSource(str, Enum):
    """Event source."""

    SWIFT_GIFTS = "swift_gifts"
    TONNEL = "tonnel"
    TON_API = "ton_api"
    FRAGMENT = "fragment"
    THERMOS = "thermos"


class Marketplace(str, Enum):
    """Marketplace where the item is listed."""

    PORTALS = "portals"
    MRKT = "mrkt"
    TONNEL = "tonnel"
    GETGEMS = "getgems"
    FRAGMENT = "fragment"
    UNKNOWN = "unknown"

    def get_gift_url(self, gift_id: str) -> str:
        """Get direct purchase URL for a gift on this marketplace.

        Uses Telegram Mini App deep links with startapp parameter
        to open the specific listing directly in the marketplace.
        """
        # Deep links to actual marketplace listings (for buying)
        urls = {
            # Portals: t.me/portals/market?startapp=<gift_id>
            "portals": f"https://t.me/portals/market?startapp={gift_id}",
            # MRKT: t.me/mrkt/app?startapp=<gift_id>
            "mrkt": f"https://t.me/mrkt/app?startapp={gift_id}",
            # Tonnel: t.me/TonnelMarketBot/market?startapp=<gift_id>
            "tonnel": f"https://t.me/TonnelMarketBot/market?startapp={gift_id}",
            # GetGems: use their web interface
            "getgems": f"https://getgems.io/nft/{gift_id}",
            # Fragment: web interface
            "fragment": f"https://fragment.com/gift/{gift_id}",
        }
        return urls.get(self.value, f"https://t.me/nft/{gift_id}")


class ConfidenceLevel(str, Enum):
    """Confidence level for analytics."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Trend(str, Enum):
    """Market trend."""

    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"


class BackgroundFilter(str, Enum):
    """Background filter options."""

    ANY = "any"
    NONE = "none"
    BLACK_PACK = "black_pack"


class AlertMode(str, Enum):
    """Alert mode."""

    SPAM = "spam"
    SNIPER = "sniper"


# Black Pack backgrounds
BLACK_PACK_BACKGROUNDS = {"Black", "Black Onyx"}


class MarketEvent(BaseModel):
    """Market event from Swift Gifts or Tonnel."""

    event_time: datetime
    event_type: EventType
    gift_id: str
    gift_name: Optional[str] = None
    model: Optional[str] = None
    backdrop: Optional[str] = None
    pattern: Optional[str] = None
    number: Optional[int] = None
    price: Decimal
    price_old: Optional[Decimal] = None
    photo_url: Optional[str] = None
    source: EventSource
    marketplace: Optional[Marketplace] = None
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def marketplace_url(self) -> str:
        """Get URL to view this item on marketplace."""
        if self.marketplace:
            return self.marketplace.get_gift_url(self.gift_id)
        return ""

    @property
    def asset_key(self) -> str:
        """Generate asset key for grouping."""
        backdrop_key = self.backdrop if self.backdrop else "no_bg"
        if self.number is not None:
            return f"{self.model}:{backdrop_key}:{self.number}"
        return f"{self.model}:{backdrop_key}"

    @property
    def is_black_pack(self) -> bool:
        """Check if this event is for black pack."""
        return self.backdrop in BLACK_PACK_BACKGROUNDS

    @field_validator("price", "price_old", mode="before")
    @classmethod
    def validate_decimal(cls, v):
        """Convert to Decimal if needed."""
        if v is None:
            return v
        return Decimal(str(v))


class ActiveListing(BaseModel):
    """Active listing on the market."""

    id: Optional[int] = None
    gift_id: str
    gift_name: Optional[str] = None
    model: Optional[str] = None
    backdrop: Optional[str] = None
    pattern: Optional[str] = None
    number: Optional[int] = None
    price: Decimal
    listed_at: Optional[datetime] = None
    export_at: Optional[datetime] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    source: EventSource
    raw_data: Optional[Dict[str, Any]] = None

    @property
    def asset_key(self) -> str:
        """Generate asset key."""
        backdrop_key = self.backdrop if self.backdrop else "no_bg"
        if self.number is not None:
            return f"{self.model}:{backdrop_key}:{self.number}"
        return f"{self.model}:{backdrop_key}"

    @property
    def is_black_pack(self) -> bool:
        """Check if black pack."""
        return self.backdrop in BLACK_PACK_BACKGROUNDS

    @field_validator("price", mode="before")
    @classmethod
    def validate_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        return Decimal(str(v))


class FloorData(BaseModel):
    """Floor price data."""

    first: Optional[Decimal] = None
    second: Optional[Decimal] = None
    third: Optional[Decimal] = None
    count: int = 0

    @field_validator("first", "second", "third", mode="before")
    @classmethod
    def validate_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        return Decimal(str(v))


class AssetAnalytics(BaseModel):
    """Analytics for an asset."""

    asset_key: str
    floor_1st: Optional[Decimal] = None
    floor_2nd: Optional[Decimal] = None
    floor_3rd: Optional[Decimal] = None
    listings_count: int = 0
    sales_7d: int = 0
    sales_30d: int = 0
    price_q25: Optional[Decimal] = None
    price_q50: Optional[Decimal] = None
    price_q75: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    liquidity_score: Optional[Decimal] = None
    confidence_level: Optional[ConfidenceLevel] = None
    last_sale_at: Optional[datetime] = None
    trend: Optional[Trend] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator(
        "floor_1st",
        "floor_2nd",
        "floor_3rd",
        "price_q25",
        "price_q50",
        "price_q75",
        "price_max",
        "liquidity_score",
        mode="before",
    )
    @classmethod
    def validate_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        return Decimal(str(v))


class UserSettings(BaseModel):
    """User settings and filters."""

    user_id: int
    mode: AlertMode = AlertMode.SPAM
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None
    profit_min: int = 12
    background_filter: BackgroundFilter = BackgroundFilter.ANY
    criterion: str = "auto"
    rarity_min: Optional[int] = None
    rarity_max: Optional[int] = None
    clean_only: bool = False
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Alert(BaseModel):
    """Alert to send to user."""

    asset_key: str
    gift_id: str
    gift_name: Optional[str] = None
    model: Optional[str] = None
    backdrop: Optional[str] = None
    number: Optional[int] = None
    price: Decimal
    profit_pct: Decimal
    reference_price: Decimal
    reference_type: str  # "TG avg (CAD)", "2nd floor black_pack", etc
    hotness: Decimal
    liquidity_score: Decimal
    confidence_level: ConfidenceLevel
    floor_black_pack: Optional[Decimal] = None
    floor_general: Optional[Decimal] = None
    sales_q25: Optional[Decimal] = None
    sales_q75: Optional[Decimal] = None
    sales_max: Optional[Decimal] = None
    sales_48h: int = 0
    is_priority: bool = False
    photo_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)  # Alert creation time
    event_time: Optional[datetime] = None  # Original event time from market
    source: EventSource
    event_type: EventType
    marketplace: Optional[Marketplace] = None

    # Telegram statistics (когда доступны)
    tg_floor_price: Optional[Decimal] = None  # Минимальная цена в TON
    tg_avg_price: Optional[Decimal] = None    # Средняя цена в TON
    tg_max_price: Optional[Decimal] = None    # Расчётная макс. цена в TON
    tg_listed_count: Optional[int] = None     # Количество листингов

    @property
    def marketplace_url(self) -> str:
        """Get URL to view this item on marketplace."""
        if self.marketplace:
            return self.marketplace.get_gift_url(self.gift_id)
        return ""

    @property
    def is_black_pack(self) -> bool:
        """Check if black pack."""
        return self.backdrop in BLACK_PACK_BACKGROUNDS

    @field_validator(
        "price",
        "profit_pct",
        "reference_price",
        "hotness",
        "liquidity_score",
        "floor_black_pack",
        "floor_general",
        "sales_q25",
        "sales_q75",
        "sales_max",
        "tg_floor_price",
        "tg_avg_price",
        "tg_max_price",
        mode="before",
    )
    @classmethod
    def validate_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        return Decimal(str(v))
