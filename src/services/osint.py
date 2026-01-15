"""OSINT service for user lookup and gift history analysis."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from decimal import Decimal

from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.types import User, UserFull

from src.services.telegram_client import tg_client_manager
from src.services.ton_api import ton_api, NFTGift

logger = logging.getLogger(__name__)


@dataclass
class GiftInfo:
    """Information about a single gift."""
    gift_id: str
    name: str
    date: datetime
    stars: int
    from_user_id: Optional[int] = None
    from_username: Optional[str] = None
    from_name: Optional[str] = None
    is_saved: bool = False
    is_hidden: bool = False
    model: Optional[str] = None
    backdrop: Optional[str] = None
    symbol: Optional[str] = None


@dataclass
class UserProfile:
    """User profile information."""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_premium: bool = False
    is_bot: bool = False
    is_verified: bool = False
    phone: Optional[str] = None
    bio: Optional[str] = None

    @property
    def full_name(self) -> str:
        parts = [self.first_name or ""]
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts).strip() or "Unknown"

    @property
    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        return f"[ID: {self.user_id}]"


@dataclass
class GiftStats:
    """Statistics about user's gifts."""
    total_gifts: int = 0
    total_stars: int = 0
    unique_senders: int = 0
    gifts_by_sender: dict = field(default_factory=dict)

    def add_gift(self, gift: GiftInfo):
        self.total_gifts += 1
        self.total_stars += gift.stars

        sender_key = gift.from_user_id or "unknown"
        if sender_key not in self.gifts_by_sender:
            self.gifts_by_sender[sender_key] = {
                "user_id": gift.from_user_id,
                "username": gift.from_username,
                "name": gift.from_name,
                "gifts": [],
                "total_stars": 0
            }

        self.gifts_by_sender[sender_key]["gifts"].append(gift)
        self.gifts_by_sender[sender_key]["total_stars"] += gift.stars

        self.unique_senders = len([k for k in self.gifts_by_sender if k != "unknown"])


@dataclass
class OSINTReport:
    """Complete OSINT report for a user."""
    profile: UserProfile
    gifts_received: list[GiftInfo] = field(default_factory=list)
    stats: GiftStats = field(default_factory=GiftStats)
    # TON blockchain data
    ton_address: Optional[str] = None
    ton_balance: float = 0.0
    nft_gifts: list[NFTGift] = field(default_factory=list)
    error: Optional[str] = None

    def format_telegram_message(self) -> str:
        """Format report as Telegram message."""
        lines = []

        # Profile section
        lines.append(f"👤 <b>Профиль пользователя</b>")
        lines.append(f"├ Имя: {self.profile.full_name}")
        lines.append(f"├ Username: {self.profile.mention}")
        lines.append(f"├ ID: <code>{self.profile.user_id}</code>")
        lines.append(f"├ Premium: {'✅ Да' if self.profile.is_premium else '❌ Нет'}")
        lines.append(f"├ Бот: {'🤖 Да' if self.profile.is_bot else '👤 Нет'}")
        if self.profile.bio:
            bio_short = self.profile.bio[:100] + "..." if len(self.profile.bio) > 100 else self.profile.bio
            lines.append(f"└ Bio: {bio_short}")
        else:
            lines.append(f"└ Bio: -")

        lines.append("")

        # Stats section
        lines.append(f"📊 <b>Статистика подарков</b>")
        lines.append(f"├ Публичных подарков: {self.stats.total_gifts}")
        lines.append(f"├ Общая стоимость: {self.stats.total_stars}⭐️")
        lines.append(f"├ Уникальных отправителей: {self.stats.unique_senders}")
        lines.append(f"└ <i>Показаны только подарки, сохранённые в профиле</i>")

        # Top senders
        if self.stats.gifts_by_sender:
            lines.append("")
            lines.append(f"🎁 <b>Подарки по отправителям</b>")

            # Sort by total stars
            sorted_senders = sorted(
                self.stats.gifts_by_sender.values(),
                key=lambda x: x["total_stars"],
                reverse=True
            )[:5]  # Top 5

            for i, sender in enumerate(sorted_senders, 1):
                sender_name = sender["name"] or "Unknown"
                sender_mention = f"@{sender['username']}" if sender["username"] else f"[ID: {sender['user_id']}]"
                gift_count = len(sender["gifts"])
                total_stars = sender["total_stars"]

                lines.append(f"")
                lines.append(f"┌─ #{i} {sender_mention}")
                lines.append(f"├─ 👤 {sender_name}")
                lines.append(f"├─ 📦 Подарков: {gift_count} на {total_stars}⭐️")

                # Show last 3 gifts from this sender
                recent_gifts = sorted(sender["gifts"], key=lambda g: g.date, reverse=True)[:3]
                for j, gift in enumerate(recent_gifts):
                    date_str = gift.date.strftime("%d.%m.%Y %H:%M")
                    prefix = "└─" if j == len(recent_gifts) - 1 else "├─"
                    lines.append(f"{prefix} 🎁 {gift.stars}⭐️ • {date_str}")

        # TON blockchain section
        if self.ton_address:
            lines.append("")
            lines.append(f"💎 <b>TON Кошелёк</b>")
            # Сокращаем адрес для отображения
            short_addr = f"{self.ton_address[:6]}...{self.ton_address[-4:]}"
            lines.append(f"├ Адрес: <code>{short_addr}</code>")
            lines.append(f"├ Баланс: {self.ton_balance:.2f} TON")
            lines.append(f"└ NFT подарков: {len(self.nft_gifts)}")

            # Show NFT gifts
            if self.nft_gifts:
                lines.append("")
                lines.append(f"🖼 <b>NFT Подарки на блокчейне</b>")
                for i, nft in enumerate(self.nft_gifts[:5], 1):  # Top 5
                    price_str = f" • {nft.last_sale_price:.2f} TON" if nft.last_sale_price else ""
                    prefix = "└" if i == min(5, len(self.nft_gifts)) else "├"
                    lines.append(f"{prefix} {nft.name}{price_str}")

                if len(self.nft_gifts) > 5:
                    lines.append(f"  <i>...и ещё {len(self.nft_gifts) - 5}</i>")
        else:
            lines.append("")
            lines.append(f"💎 <b>TON Кошелёк</b>")
            lines.append(f"└ <i>Не найден (нет привязки username.t.me)</i>")

        return "\n".join(lines)


class OSINTService:
    """Service for performing OSINT lookups on Telegram users."""

    async def lookup_user(self, username_or_id: str | int) -> OSINTReport:
        """
        Perform OSINT lookup on a user.

        Args:
            username_or_id: Username (with or without @) or user ID

        Returns:
            OSINTReport with all gathered information
        """
        # Get Telegram client (get_client handles its own locking)
        logger.info(f"OSINT: Starting lookup for {username_or_id}")
        client = await tg_client_manager.get_client()
        logger.info(f"OSINT: Got client: {client is not None}")
        if not client:
            return OSINTReport(
                profile=UserProfile(user_id=0),
                error="Telegram client not available"
            )

        try:
            # Resolve user
            logger.info(f"OSINT: Resolving entity for {username_or_id}")
            if isinstance(username_or_id, str):
                # Remove @ if present
                username_or_id = username_or_id.lstrip("@")

                # Try to parse as int
                try:
                    user_id = int(username_or_id)
                    entity = await client.get_entity(user_id)
                except ValueError:
                    entity = await client.get_entity(username_or_id)
            else:
                entity = await client.get_entity(username_or_id)
            logger.info(f"OSINT: Entity resolved: {entity}")

            if not isinstance(entity, User):
                return OSINTReport(
                    profile=UserProfile(user_id=0),
                    error="Not a user (might be a channel or chat)"
                )

            # Get full user info
            full_user_result = await client(GetFullUserRequest(entity))
            full_user: UserFull = full_user_result.full_user
            user: User = full_user_result.users[0]

            # Build profile
            profile = UserProfile(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_premium=user.premium or False,
                is_bot=user.bot or False,
                is_verified=user.verified or False,
                bio=full_user.about
            )

            # Get gifts received by user
            gifts_received = []
            stats = GiftStats()

            try:
                # Get star gifts for this user with pagination
                offset = ""
                total_fetched = 0

                while True:
                    gifts_result = await client(GetSavedStarGiftsRequest(
                        peer=entity,
                        offset=offset,
                        limit=100
                    ))

                    logger.info(f"OSINT: Got {len(gifts_result.gifts)} gifts (offset={offset})")

                    # Debug: log raw gift structure for first gift
                    if gifts_result.gifts and total_fetched == 0:
                        first_gift = gifts_result.gifts[0]
                        logger.debug(f"OSINT: First gift structure: {first_gift}")

                    # Build user cache from result.users for sender resolution
                    users_cache = {}
                    if hasattr(gifts_result, 'users'):
                        for u in gifts_result.users:
                            users_cache[u.id] = u
                            logger.debug(f"OSINT: Cached user {u.id}: @{getattr(u, 'username', None)}")

                    for gift in gifts_result.gifts:
                        # Extract gift info
                        gift_info = self._parse_gift(gift, users_cache)
                        if gift_info:
                            gifts_received.append(gift_info)
                            stats.add_gift(gift_info)
                            total_fetched += 1

                    # Check for more pages
                    next_offset = getattr(gifts_result, 'next_offset', None)
                    if not next_offset or not gifts_result.gifts:
                        break
                    offset = next_offset

                logger.info(f"OSINT: Total gifts fetched: {total_fetched}")

            except Exception as e:
                logger.warning(f"Failed to get gifts for user: {e}", exc_info=True)

            # Get TON blockchain data
            ton_address = None
            ton_balance = 0.0
            nft_gifts = []

            try:
                # Пробуем резолвить TON адрес через username
                if profile.username:
                    logger.info(f"OSINT: Resolving TON address for @{profile.username}")
                    ton_address = await ton_api.resolve_domain(profile.username)

                    if ton_address:
                        logger.info(f"OSINT: Found TON address: {ton_address}")
                        wallet_info = await ton_api.get_wallet_info(ton_address)
                        if wallet_info:
                            ton_balance = wallet_info.balance
                            nft_gifts = wallet_info.gift_nfts
                            logger.info(
                                f"OSINT: TON wallet - balance: {ton_balance:.2f}, "
                                f"NFT gifts: {len(nft_gifts)}"
                            )
                    else:
                        logger.info(f"OSINT: No TON address found for @{profile.username}")

            except Exception as e:
                logger.warning(f"Failed to get TON data: {e}", exc_info=True)

            return OSINTReport(
                profile=profile,
                gifts_received=gifts_received,
                stats=stats,
                ton_address=ton_address,
                ton_balance=ton_balance,
                nft_gifts=nft_gifts
            )

        except Exception as e:
            logger.error(f"OSINT lookup failed: {e}", exc_info=True)
            return OSINTReport(
                profile=UserProfile(user_id=0),
                error=str(e)
            )

    def _parse_gift(self, gift, users_cache: dict = None) -> Optional[GiftInfo]:
        """Parse a gift object from Telegram API."""
        try:
            # Extract basic info
            gift_id = getattr(gift, 'slug', None) or str(getattr(gift, 'id', 'unknown'))

            # Get gift details
            star_gift = getattr(gift, 'gift', None)
            stars = getattr(star_gift, 'stars', 0) if star_gift else 0

            # Get date
            date = getattr(gift, 'date', None)
            if date and isinstance(date, int):
                date = datetime.fromtimestamp(date)
            elif not date:
                date = datetime.now()

            # Get sender info
            from_id = getattr(gift, 'from_id', None)
            from_user_id = None
            from_username = None
            from_name = None

            if from_id:
                # from_id может быть PeerUser объектом
                from_user_id = getattr(from_id, 'user_id', None)

                # Пытаемся найти пользователя в кэше
                if from_user_id and users_cache and from_user_id in users_cache:
                    sender = users_cache[from_user_id]
                    from_username = getattr(sender, 'username', None)
                    first = getattr(sender, 'first_name', '') or ''
                    last = getattr(sender, 'last_name', '') or ''
                    from_name = f"{first} {last}".strip() or None

            # Check if name is hidden
            name_hidden = getattr(gift, 'name_hidden', False)
            if name_hidden:
                from_name = "Скрыто"
                from_username = None

            # Get saved/hidden status
            is_saved = not getattr(gift, 'unsaved', True)

            logger.debug(
                f"OSINT: Parsed gift {gift_id}: {stars}⭐ from "
                f"user_id={from_user_id} @{from_username} ({from_name})"
            )

            return GiftInfo(
                gift_id=gift_id,
                name=getattr(star_gift, 'title', 'Gift') if star_gift else 'Gift',
                date=date,
                stars=stars,
                from_user_id=from_user_id,
                from_username=from_username,
                from_name=from_name,
                is_saved=is_saved
            )

        except Exception as e:
            logger.warning(f"Failed to parse gift: {e}", exc_info=True)
            return None


# Global instance
osint_service = OSINTService()
