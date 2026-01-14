-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Market events (hypertable for time-series data)
CREATE TABLE IF NOT EXISTS market_events (
    id BIGSERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(20) NOT NULL, -- buy, listing, change_price
    gift_id VARCHAR(50) NOT NULL,
    gift_name VARCHAR(100),
    model VARCHAR(50),
    backdrop VARCHAR(50),
    pattern VARCHAR(50),
    number INTEGER,
    price DECIMAL(12, 2),
    price_old DECIMAL(12, 2),
    source VARCHAR(20), -- swift_gifts, tonnel
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (event_time, id)
);

-- Convert to hypertable
SELECT create_hypertable('market_events', 'event_time', if_not_exists => TRUE);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_events_gift_id ON market_events(gift_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON market_events(event_type, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_model ON market_events(model, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_backdrop ON market_events(backdrop, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_black_pack ON market_events(backdrop, event_time DESC)
    WHERE backdrop IN ('Black', 'Black Onyx');

-- Active listings (current market state)
CREATE TABLE IF NOT EXISTS active_listings (
    id BIGSERIAL PRIMARY KEY,
    gift_id VARCHAR(50) UNIQUE NOT NULL,
    gift_name VARCHAR(100),
    model VARCHAR(50),
    backdrop VARCHAR(50),
    pattern VARCHAR(50),
    number INTEGER,
    price DECIMAL(12, 2),
    listed_at TIMESTAMPTZ,
    export_at TIMESTAMPTZ,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    source VARCHAR(20),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_listings_model ON active_listings(model);
CREATE INDEX IF NOT EXISTS idx_listings_backdrop ON active_listings(backdrop);
CREATE INDEX IF NOT EXISTS idx_listings_price ON active_listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_model_backdrop ON active_listings(model, backdrop);

-- Asset analytics (cached calculations)
CREATE TABLE IF NOT EXISTS asset_analytics (
    asset_key VARCHAR(200) PRIMARY KEY,
    floor_1st DECIMAL(12, 2),
    floor_2nd DECIMAL(12, 2),
    floor_3rd DECIMAL(12, 2),
    listings_count INTEGER DEFAULT 0,
    sales_7d INTEGER DEFAULT 0,
    sales_30d INTEGER DEFAULT 0,
    price_q25 DECIMAL(12, 2),
    price_q50 DECIMAL(12, 2),
    price_q75 DECIMAL(12, 2),
    price_max DECIMAL(12, 2),
    liquidity_score DECIMAL(3, 1),
    confidence_level VARCHAR(20),
    last_sale_at TIMESTAMPTZ,
    trend VARCHAR(20),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analytics_updated ON asset_analytics(updated_at);

-- User settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY,
    mode VARCHAR(20) DEFAULT 'spam', -- spam, sniper
    price_min DECIMAL(12, 2),
    price_max DECIMAL(12, 2),
    profit_min INTEGER DEFAULT 12,
    background_filter VARCHAR(20) DEFAULT 'any', -- any, none, black_pack
    criterion VARCHAR(20) DEFAULT 'auto', -- auto, general, no_bg, black_pack
    rarity_min INTEGER,
    rarity_max INTEGER,
    clean_only BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watchlist
CREATE TABLE IF NOT EXISTS watchlist (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    asset_key VARCHAR(200) NOT NULL,
    profit_threshold INTEGER,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, asset_key)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);

-- Muted assets
CREATE TABLE IF NOT EXISTS muted_assets (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    asset_key VARCHAR(200) NOT NULL,
    muted_until TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, asset_key)
);

CREATE INDEX IF NOT EXISTS idx_muted_expires ON muted_assets(muted_until);
CREATE INDEX IF NOT EXISTS idx_muted_user ON muted_assets(user_id, muted_until);

-- Sent alerts (for cooldown tracking)
CREATE TABLE IF NOT EXISTS sent_alerts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    asset_key VARCHAR(200) NOT NULL,
    event_id BIGINT,
    profit_pct DECIMAL(5, 2),
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_cooldown ON sent_alerts(user_id, asset_key, sent_at DESC);

-- Retention policy: keep events for 90 days
SELECT add_retention_policy('market_events', INTERVAL '90 days', if_not_exists => TRUE);

-- Continuous aggregate for hourly stats (optional, for performance)
CREATE MATERIALIZED VIEW IF NOT EXISTS hourly_market_stats
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', event_time) AS hour,
    model,
    backdrop,
    event_type,
    COUNT(*) as event_count,
    AVG(price) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price
FROM market_events
GROUP BY hour, model, backdrop, event_type
WITH NO DATA;

-- Refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy('hourly_market_stats',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Helper function to clean old muted entries
CREATE OR REPLACE FUNCTION clean_expired_mutes()
RETURNS void AS $$
BEGIN
    DELETE FROM muted_assets WHERE muted_until < NOW();
END;
$$ LANGUAGE plpgsql;

-- Helper function to get asset key from event
CREATE OR REPLACE FUNCTION get_asset_key(p_model VARCHAR, p_backdrop VARCHAR, p_number INTEGER)
RETURNS VARCHAR AS $$
BEGIN
    IF p_number IS NOT NULL THEN
        RETURN p_model || ':' || COALESCE(p_backdrop, 'no_bg') || ':' || p_number;
    ELSE
        RETURN p_model || ':' || COALESCE(p_backdrop, 'no_bg');
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE market_events IS 'Time-series data of all market events (buy, listing, change_price)';
COMMENT ON TABLE active_listings IS 'Current active listings on the market';
COMMENT ON TABLE asset_analytics IS 'Cached analytics calculations for each asset';
COMMENT ON TABLE user_settings IS 'User preferences and filter settings';
COMMENT ON TABLE watchlist IS 'Assets that users are watching';
COMMENT ON TABLE muted_assets IS 'Temporarily muted assets per user';
COMMENT ON TABLE sent_alerts IS 'Alert history for cooldown management';
