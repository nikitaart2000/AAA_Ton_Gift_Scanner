/**
 * TypeScript types for TON Gifts Terminal
 */

export interface Deal {
  asset_key: string;
  gift_id: string;
  gift_name: string;
  model?: string;
  backdrop?: string;
  pattern?: string;
  number?: number;
  photo_url?: string;
  price: number;
  reference_price: number;
  reference_type: string;
  profit_pct: number;
  confidence_level: 'very_high' | 'high' | 'medium' | 'low';
  liquidity_score: number;
  hotness: number;
  sales_48h: number;
  event_type: 'buy' | 'listing' | 'change_price';
  event_time: string;
  source: 'swift_gifts' | 'tonnel';
  is_black_pack: boolean;
  is_priority: boolean;
  quality_badge?: 'GEM' | 'HOT' | 'BLACK_PACK' | 'SNIPER';
}

export interface MarketOverview {
  active_deals: number;
  hot_deals: number;
  priority_deals: number;
  black_pack_floor?: number;
  general_floor?: number;
  market_trend: 'rising' | 'falling' | 'stable';
  last_updated: string;
}

export interface DealsResponse {
  deals: Deal[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}
