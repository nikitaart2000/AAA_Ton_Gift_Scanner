"""Gift history database models and operations.

Stores:
- NFT transfer history (blockchain events)
- Username <-> Wallet address mappings
- Gift metadata cache
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Numeric,
    Boolean, Text, Index, select, and_, or_
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


class NFTTransfer(Base):
    """NFT transfer event from blockchain."""
    __tablename__ = "nft_transfers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(64), unique=True, nullable=False, index=True)

    # NFT info
    nft_address = Column(String(66), nullable=False, index=True)
    nft_name = Column(String(255))
    collection_address = Column(String(66), index=True)
    collection_name = Column(String(255))

    # Transfer details
    from_address = Column(String(66), nullable=False, index=True)
    to_address = Column(String(66), nullable=False, index=True)
    price_ton = Column(Numeric(20, 9))  # Price if it was a sale

    # Timestamps
    block_timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Flags
    is_telegram_gift = Column(Boolean, default=False, index=True)
    is_sale = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_nft_transfers_from_to", "from_address", "to_address"),
        Index("ix_nft_transfers_collection_time", "collection_address", "block_timestamp"),
    )


class WalletUsername(Base):
    """Mapping between TON wallet address and Telegram username."""
    __tablename__ = "wallet_usernames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(66), unique=True, nullable=False, index=True)
    username = Column(String(64), index=True)
    user_id = Column(BigInteger, index=True)
    user_name = Column(String(255))  # Full name

    # How we discovered this mapping
    source = Column(String(50))  # "ton_dns", "gift_metadata", "manual"

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_verified = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_wallet_usernames_user", "username", "user_id"),
    )


class GiftMetadataCache(Base):
    """Cache for Fragment gift NFT metadata."""
    __tablename__ = "gift_metadata_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255))
    description = Column(Text)

    # Visual assets
    image_url = Column(Text)
    animation_url = Column(Text)

    # Traits
    model = Column(String(100), index=True)
    backdrop = Column(String(100), index=True)
    symbol = Column(String(100))

    # Original sender/recipient (if available)
    sender_id = Column(BigInteger, index=True)
    sender_username = Column(String(64))
    recipient_id = Column(BigInteger, index=True)
    recipient_username = Column(String(64))
    transfer_date = Column(DateTime)
    original_message = Column(Text)

    # Cache timestamps
    fetched_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)

    __table_args__ = (
        Index("ix_gift_metadata_sender", "sender_id", "sender_username"),
        Index("ix_gift_metadata_recipient", "recipient_id", "recipient_username"),
    )


class GiftHistoryService:
    """Service for managing gift history in database."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def record_transfer(
        self,
        tx_hash: str,
        nft_address: str,
        from_address: str,
        to_address: str,
        block_timestamp: datetime,
        nft_name: Optional[str] = None,
        collection_address: Optional[str] = None,
        collection_name: Optional[str] = None,
        price_ton: Optional[Decimal] = None,
        is_telegram_gift: bool = False
    ) -> bool:
        """
        Record an NFT transfer event.

        Returns True if recorded, False if duplicate.
        """
        try:
            async with self.session_factory() as session:
                # Check for duplicate
                existing = await session.execute(
                    select(NFTTransfer).where(NFTTransfer.tx_hash == tx_hash)
                )
                if existing.scalar_one_or_none():
                    return False

                transfer = NFTTransfer(
                    tx_hash=tx_hash,
                    nft_address=nft_address,
                    nft_name=nft_name,
                    collection_address=collection_address,
                    collection_name=collection_name,
                    from_address=from_address,
                    to_address=to_address,
                    price_ton=price_ton,
                    block_timestamp=block_timestamp,
                    is_telegram_gift=is_telegram_gift,
                    is_sale=price_ton is not None
                )

                session.add(transfer)
                await session.commit()

                logger.debug(f"Recorded transfer: {tx_hash[:16]}...")
                return True

        except Exception as e:
            logger.error(f"Failed to record transfer: {e}")
            return False

    async def get_transfers_by_wallet(
        self,
        wallet_address: str,
        limit: int = 100,
        include_sent: bool = True,
        include_received: bool = True,
        telegram_gifts_only: bool = False
    ) -> list[NFTTransfer]:
        """Get NFT transfers involving a wallet."""
        try:
            async with self.session_factory() as session:
                conditions = []

                if include_sent and include_received:
                    conditions.append(
                        or_(
                            NFTTransfer.from_address == wallet_address,
                            NFTTransfer.to_address == wallet_address
                        )
                    )
                elif include_sent:
                    conditions.append(NFTTransfer.from_address == wallet_address)
                elif include_received:
                    conditions.append(NFTTransfer.to_address == wallet_address)

                if telegram_gifts_only:
                    conditions.append(NFTTransfer.is_telegram_gift == True)

                query = (
                    select(NFTTransfer)
                    .where(and_(*conditions))
                    .order_by(NFTTransfer.block_timestamp.desc())
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get transfers: {e}")
            return []

    async def link_wallet_username(
        self,
        wallet_address: str,
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        source: str = "ton_dns"
    ) -> bool:
        """Link a wallet address to a Telegram username/user_id."""
        try:
            async with self.session_factory() as session:
                # Check existing
                existing = await session.execute(
                    select(WalletUsername)
                    .where(WalletUsername.wallet_address == wallet_address)
                )
                record = existing.scalar_one_or_none()

                if record:
                    # Update existing
                    if username:
                        record.username = username
                    if user_id:
                        record.user_id = user_id
                    if user_name:
                        record.user_name = user_name
                    record.last_verified = datetime.utcnow()
                else:
                    # Create new
                    record = WalletUsername(
                        wallet_address=wallet_address,
                        username=username,
                        user_id=user_id,
                        user_name=user_name,
                        source=source
                    )
                    session.add(record)

                await session.commit()
                logger.debug(f"Linked wallet {wallet_address[:16]}... to @{username}")
                return True

        except Exception as e:
            logger.error(f"Failed to link wallet: {e}")
            return False

    async def get_wallet_by_username(self, username: str) -> Optional[str]:
        """Get wallet address for a username."""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(WalletUsername.wallet_address)
                    .where(WalletUsername.username == username.lstrip("@"))
                )
                row = result.scalar_one_or_none()
                return row

        except Exception as e:
            logger.error(f"Failed to get wallet by username: {e}")
            return None

    async def get_username_by_wallet(self, wallet_address: str) -> Optional[dict]:
        """Get username/user_id for a wallet address."""
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(WalletUsername)
                    .where(WalletUsername.wallet_address == wallet_address)
                )
                record = result.scalar_one_or_none()

                if record:
                    return {
                        "username": record.username,
                        "user_id": record.user_id,
                        "user_name": record.user_name,
                        "source": record.source
                    }
                return None

        except Exception as e:
            logger.error(f"Failed to get username by wallet: {e}")
            return None

    async def cache_gift_metadata(
        self,
        slug: str,
        name: str,
        model: Optional[str] = None,
        backdrop: Optional[str] = None,
        symbol: Optional[str] = None,
        sender_id: Optional[int] = None,
        sender_username: Optional[str] = None,
        recipient_id: Optional[int] = None,
        recipient_username: Optional[str] = None,
        image_url: Optional[str] = None,
        animation_url: Optional[str] = None,
        description: Optional[str] = None,
        transfer_date: Optional[datetime] = None,
        original_message: Optional[str] = None,
        ttl_hours: int = 24
    ) -> bool:
        """Cache gift metadata from Fragment."""
        try:
            async with self.session_factory() as session:
                from datetime import timedelta

                existing = await session.execute(
                    select(GiftMetadataCache).where(GiftMetadataCache.slug == slug)
                )
                record = existing.scalar_one_or_none()

                now = datetime.utcnow()
                expires = now + timedelta(hours=ttl_hours)

                if record:
                    record.name = name
                    record.model = model
                    record.backdrop = backdrop
                    record.symbol = symbol
                    record.sender_id = sender_id
                    record.sender_username = sender_username
                    record.recipient_id = recipient_id
                    record.recipient_username = recipient_username
                    record.image_url = image_url
                    record.animation_url = animation_url
                    record.description = description
                    record.transfer_date = transfer_date
                    record.original_message = original_message
                    record.fetched_at = now
                    record.expires_at = expires
                else:
                    record = GiftMetadataCache(
                        slug=slug,
                        name=name,
                        model=model,
                        backdrop=backdrop,
                        symbol=symbol,
                        sender_id=sender_id,
                        sender_username=sender_username,
                        recipient_id=recipient_id,
                        recipient_username=recipient_username,
                        image_url=image_url,
                        animation_url=animation_url,
                        description=description,
                        transfer_date=transfer_date,
                        original_message=original_message,
                        fetched_at=now,
                        expires_at=expires
                    )
                    session.add(record)

                await session.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to cache gift metadata: {e}")
            return False

    async def get_gifts_sent_by_user(
        self,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        limit: int = 100
    ) -> list[GiftMetadataCache]:
        """Get gifts sent by a user (from metadata)."""
        try:
            async with self.session_factory() as session:
                conditions = []

                if user_id:
                    conditions.append(GiftMetadataCache.sender_id == user_id)
                if username:
                    conditions.append(
                        GiftMetadataCache.sender_username == username.lstrip("@")
                    )

                if not conditions:
                    return []

                query = (
                    select(GiftMetadataCache)
                    .where(or_(*conditions))
                    .order_by(GiftMetadataCache.transfer_date.desc())
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get gifts sent by user: {e}")
            return []

    async def get_gifts_received_by_user(
        self,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        limit: int = 100
    ) -> list[GiftMetadataCache]:
        """Get gifts received by a user (from metadata)."""
        try:
            async with self.session_factory() as session:
                conditions = []

                if user_id:
                    conditions.append(GiftMetadataCache.recipient_id == user_id)
                if username:
                    conditions.append(
                        GiftMetadataCache.recipient_username == username.lstrip("@")
                    )

                if not conditions:
                    return []

                query = (
                    select(GiftMetadataCache)
                    .where(or_(*conditions))
                    .order_by(GiftMetadataCache.transfer_date.desc())
                    .limit(limit)
                )

                result = await session.execute(query)
                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Failed to get gifts received by user: {e}")
            return []


# SQL to create tables (run once)
CREATE_TABLES_SQL = """
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

CREATE INDEX IF NOT EXISTS ix_nft_transfers_tx_hash ON nft_transfers(tx_hash);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_nft_address ON nft_transfers(nft_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_collection_address ON nft_transfers(collection_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_from_address ON nft_transfers(from_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_to_address ON nft_transfers(to_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_block_timestamp ON nft_transfers(block_timestamp);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_is_telegram_gift ON nft_transfers(is_telegram_gift);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_from_to ON nft_transfers(from_address, to_address);
CREATE INDEX IF NOT EXISTS ix_nft_transfers_collection_time ON nft_transfers(collection_address, block_timestamp);

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

CREATE INDEX IF NOT EXISTS ix_wallet_usernames_wallet_address ON wallet_usernames(wallet_address);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_username ON wallet_usernames(username);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_user_id ON wallet_usernames(user_id);
CREATE INDEX IF NOT EXISTS ix_wallet_usernames_user ON wallet_usernames(username, user_id);

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

CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_slug ON gift_metadata_cache(slug);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_model ON gift_metadata_cache(model);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_backdrop ON gift_metadata_cache(backdrop);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_sender_id ON gift_metadata_cache(sender_id);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_cache_recipient_id ON gift_metadata_cache(recipient_id);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_sender ON gift_metadata_cache(sender_id, sender_username);
CREATE INDEX IF NOT EXISTS ix_gift_metadata_recipient ON gift_metadata_cache(recipient_id, recipient_username);
"""
