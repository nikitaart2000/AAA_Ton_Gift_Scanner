-- Migration: Add gift history tables for enhanced OSINT
-- Run this on your PostgreSQL database

-- Table for storing NFT transfer events from blockchain
CREATE TABLE IF NOT EXISTS nft_transfers (
    id SERIAL PRIMARY KEY,
    tx_hash VARCHAR(64) UNIQUE NOT NULL,
    nft_address VARCHAR(66) NOT NULL,
    nft_name VARCHAR(255),
    collection_address VARCHAR(66),
    collection_name VARCHAR(255),
    from_address VARCHAR(66) NOT NULL,
    to_address VARCHAR(66) NOT NULL,
    price_ton NUMERIC(20, 9),
    block_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_telegram_gift BOOLEAN DEFAULT FALSE,
    is_sale BOOLEAN DEFAULT FALSE
);

-- Indexes for nft_transfers
CREATE INDEX IF NOT EXISTS ix_nft_transfers_tx_hash ON nft_transfers(tx_hash);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_nft_address ON nft_transfers(nft_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_collection_address ON nft_transfers(collection_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_from_address ON nft_transfers(from_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_to_address ON nft_transfers(to_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_block_timestamp ON nft_transfers(block_timestamp);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_is_telegram_gift ON nft_transfers(is_telegram_gift);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_from_to ON nft_transfers(from_address, to_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_collection_time ON nft_transfers(collection_address, block_timestamp);

-- Table for mapping wallet addresses to Telegram usernames
CREATE TABLE IF NOT EXISTS wallet_usernames (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(66) UNIQUE NOT NULL,
    username VARCHAR(64),
    user_id BIGINT,
    user_name VARCHAR(255),
    source VARCHAR(50),
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for wallet_usernames
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_wallet_address ON wallet_usernames(wallet_address);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_username ON wallet_usernames(username);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_user_id ON wallet_usernames(user_id);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_user ON wallet_usernames(username, user_id);

-- Table for caching Fragment gift NFT metadata
CREATE TABLE IF NOT EXISTS gift_metadata_cache (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    description TEXT,
    image_url TEXT,
    animation_url TEXT,
    model VARCHAR(100),
    backdrop VARCHAR(100),
    symbol VARCHAR(100),
    sender_id BIGINT,
    sender_username VARCHAR(64),
    recipient_id BIGINT,
    recipient_username VARCHAR(64),
    transfer_date TIMESTAMP,
    original_message TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Indexes for gift_metadata_cache
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_slug ON gift_metadata_cache(slug);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_model ON gift_metadata_cache(model);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_backdrop ON gift_metadata_cache(backdrop);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_sender_id ON gift_metadata_cache(sender_id);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_recipient_id ON gift_metadata_cache(recipient_id);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_sender ON gift_metadata_cache(sender_id, sender_username);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_recipient ON gift_metadata_cache(recipient_id, recipient_username);

-- Grant permissions (adjust user as needed)
-- GRANT ALL PRIVILEGES ON TABLE nft_transfers TO scanner_user;
-- GRANT ALL PRIVILEGES ON TABLE wallet_usernames TO scanner_user;
-- GRANT ALL PRIVILEGES ON TABLE gift_metadata_cache TO scanner_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO scanner_user;
