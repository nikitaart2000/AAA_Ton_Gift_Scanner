"""API request/response models for Mini App."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field

from src.core.models import (
    EventType,
    EventSource,
    ConfidenceLevel,
    Trend,
    BackgroundFilter,
    AlertMode,
)


class DealCard(BaseModel):
    """Deal card for feed display."""

    # Identity
    asset_key: str
    gift_id: str
    gift_name: str
    model: Optional[str] = None
    backdrop: Optional[str] = None
    pattern: Optional[str] = None
    number: Optional[int] = None
    photo_url: Optional[str] = None

    # Pricing
    price: Decimal
    reference_price: Decimal
    reference_type: str
    profit_pct: Decimal

    # Quality indicators
    confidence_level: ConfidenceLevel
    liquidity_score: Decimal
    hotness: Decimal
    sales_48h: int = 0

    # Metadata
    event_type: EventType
    event_time: datetime
    source: EventSource
    is_black_pack: bool = False
    is_priority: bool = False

    # Quality badge (computed)
    quality_badge: Optional[str] = None  # "GEM", "HOT", "BLACK_PACK", "SNIPER"

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }


class DealsFeedResponse(BaseModel):
    """Response for deals feed."""

    deals: List[DealCard]
    total: int
    page: int
    page_size: int
    has_more: bool


class AssetFloor(BaseModel):
    """Floor prices for an asset."""

    first_floor: Optional[Decimal] = None
    second_floor: Optional[Decimal] = None
    third_floor: Optional[Decimal] = None


class AssetSales(BaseModel):
    """Sales statistics for an asset."""

    count_7d: int = 0
    count_30d: int = 0
    q25: Optional[Decimal] = None
    q50: Optional[Decimal] = None
    q75: Optional[Decimal] = None
    max: Optional[Decimal] = None
    avg_flip_time_hours: Optional[float] = None
    avg_flip_profit_pct: Optional[float] = None


class PricePoint(BaseModel):
    """Price point for chart."""

    timestamp: datetime
    price: Decimal
    event_type: str  # "buy", "listing", "change_price"

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }


class AssetAnalyticsResponse(BaseModel):
    """Detailed analytics for an asset."""

    asset_key: str
    gift_name: str
    model: Optional[str] = None
    backdrop: Optional[str] = None
    is_black_pack: bool = False

    # Current state
    floor: AssetFloor
    arp: Optional[Decimal] = None
    confidence_level: ConfidenceLevel
    liquidity_score: Decimal
    trend: Trend

    # Sales
    sales: AssetSales

    # Price history for chart
    price_history: List[PricePoint] = Field(default_factory=list)

    # Active listings
    active_listings_count: int = 0
    cheapest_listing: Optional[Decimal] = None

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
        }


class WatchlistItem(BaseModel):
    """Watchlist item."""

    asset_key: str
    gift_name: str
    model: Optional[str] = None
    backdrop: Optional[str] = None
    photo_url: Optional[str] = None

    # Current best listing
    current_price: Optional[Decimal] = None
    reference_price: Optional[Decimal] = None
    profit_pct: Optional[Decimal] = None

    # User threshold
    alert_threshold_pct: float = 15.0  # Alert if profit >= this

    # Last alert
    last_alert_at: Optional[datetime] = None

    added_at: datetime

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }


class WatchlistResponse(BaseModel):
    """Response for watchlist."""

    items: List[WatchlistItem]
    total: int


class UserFilters(BaseModel):
    """User filter preferences."""

    # Price
    price_min: Optional[Decimal] = None
    price_max: Optional[Decimal] = None

    # Profit
    profit_min: float = 15.0

    # Background
    background_filter: BackgroundFilter = BackgroundFilter.ANY

    # Quality
    min_liquidity: Optional[float] = None
    min_confidence: Optional[ConfidenceLevel] = None

    # Mode
    mode: AlertMode = AlertMode.SPAM


class UserSettingsResponse(BaseModel):
    """User settings response."""

    user_id: int
    filters: UserFilters


class MarketOverview(BaseModel):
    """Market overview stats."""

    active_deals: int
    hot_deals: int  # hotness >= 7
    priority_deals: int  # is_priority
    black_pack_floor: Optional[Decimal] = None
    general_floor: Optional[Decimal] = None
    market_trend: Trend = Trend.STABLE
    last_updated: datetime

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
        }


class AddToWatchlistRequest(BaseModel):
    """Request to add asset to watchlist."""

    asset_key: str
    alert_threshold_pct: float = 15.0


class MuteAssetRequest(BaseModel):
    """Request to mute an asset."""

    asset_key: str
    duration_minutes: int = 120  # Default 2 hours


class UpdateFiltersRequest(BaseModel):
    """Request to update user filters."""

    filters: UserFilters
