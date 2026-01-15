"""OSINT service for user lookup and gift history analysis.

Enhanced with:
- Fragment NFT metadata parsing
- GetGems marketplace data
- TonAPI blockchain history
- Database caching for gift history
"""

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
from src.services.fragment_metadata import fragment_metadata, FragmentGiftMetadata
from src.services.getgems_api import getgems_api, GetGemsNFT
from src.services.wallet_resolver import wallet_resolver, WalletMatch

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
    # TON blockchain data - can have multiple wallets!
    wallet_matches: list[WalletMatch] = field(default_factory=list)
    ton_address: Optional[str] = None  # Primary wallet
    ton_balance: float = 0.0
    nft_gifts: list[NFTGift] = field(default_factory=list)
    nft_history: list[dict] = field(default_factory=list)  # NFT transfer history
    # GetGems marketplace data
    getgems_nfts: list[GetGemsNFT] = field(default_factory=list)
    getgems_listed_count: int = 0
    getgems_total_value: Optional[Decimal] = None
    # Fragment metadata for gifts
    fragment_metadata: list[FragmentGiftMetadata] = field(default_factory=list)
    error: Optional[str] = None

    def format_telegram_message(self) -> str:
        """Format report as Telegram message - Барыга style."""
        lines = []

        # Header с вайбом
        lines.append(f"🔍 <b>ДОСЬЕ НА ХУЕСОСА</b>")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")

        # Profile section
        lines.append(f"👤 <b>{self.profile.full_name}</b>")
        if self.profile.username:
            lines.append(f"   └ <a href='https://t.me/{self.profile.username}'>@{self.profile.username}</a>")
        lines.append(f"🆔 <code>{self.profile.user_id}</code>")

        # Status badges
        badges = []
        if self.profile.is_premium:
            badges.append("⭐️ ПРЕМИУМ")
        if self.profile.is_bot:
            badges.append("🤖 БОТ")
        if self.profile.is_verified:
            badges.append("✅ ВЕРИФИЦИРОВАН")
        if badges:
            lines.append(f"   {' • '.join(badges)}")

        if self.profile.bio:
            bio_short = self.profile.bio[:80] + "..." if len(self.profile.bio) > 80 else self.profile.bio
            lines.append(f"📝 {bio_short}")

        lines.append(f"━━━━━━━━━━━━━━━━━━━━")

        # Gift stats section
        if self.stats.total_gifts > 0:
            lines.append("")
            lines.append(f"🎁 <b>ЧЁ НАСОБИРАЛ</b>")
            lines.append(f"📦 Подарков: {self.stats.total_gifts}")
            lines.append(f"⭐️ Звёзд нахапал: {self.stats.total_stars}")
            lines.append(f"👥 Дарителей: {self.stats.unique_senders}")

            # Top senders with vibe
            if self.stats.gifts_by_sender:
                lines.append("")
                lines.append(f"🤑 <b>КТО ДАРИЛ</b>")

                sorted_senders = sorted(
                    self.stats.gifts_by_sender.values(),
                    key=lambda x: x["total_stars"],
                    reverse=True
                )[:5]

                for i, sender in enumerate(sorted_senders, 1):
                    sender_name = sender["name"] or "Аноним"
                    if sender["username"]:
                        sender_link = f"<a href='https://t.me/{sender['username']}'>@{sender['username']}</a>"
                    elif sender["user_id"]:
                        sender_link = f"[{sender['user_id']}]"
                    else:
                        sender_link = "🥷 Скрытый"

                    gift_count = len(sender["gifts"])
                    total_stars = sender["total_stars"]

                    lines.append(f"")
                    lines.append(f"┌ #{i} {sender_link}")
                    lines.append(f"│  {sender_name}")
                    lines.append(f"├ 📦 {gift_count} шт. на {total_stars}⭐️")

                    # Show gifts
                    recent_gifts = sorted(sender["gifts"], key=lambda g: g.date, reverse=True)[:3]
                    for j, gift in enumerate(recent_gifts):
                        date_str = gift.date.strftime("%d.%m.%Y %H:%M")
                        saved = "👁" if gift.is_saved else ""
                        prefix = "└" if j == len(recent_gifts) - 1 else "├"
                        lines.append(f"{prefix} {gift.stars}⭐️ • {date_str} {saved}")
        else:
            lines.append("")
            lines.append(f"🎁 <b>ЧЁ НАСОБИРАЛ</b>")
            lines.append(f"   <i>Хуй да нихуя - подарки спрятал или нету</i>")

        # TON blockchain section
        lines.append("")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💎 <b>КОШЕЛЬКИ</b>")

        # Show all discovered wallet connections
        if self.wallet_matches:
            lines.append("")
            lines.append(f"💱 <b>Найдено связей:</b> {len(self.wallet_matches)}")
            for i, match in enumerate(self.wallet_matches, 1):
                source_icons = {
                    "ton_dns": "🌐",
                    "tonnel": "🔄",
                    "fragment": "💎",
                    "database": "📊"
                }
                icon = source_icons.get(match.source, "🔗")
                conf = "✅" if match.confidence == "high" else "⚠️" if match.confidence == "medium" else "❓"
                prefix = "└" if i == len(self.wallet_matches) else "├"
                lines.append(f"{prefix} {icon} {match.source}: {conf}")
                lines.append(f"│  <code>{match.wallet_address}</code>")
                if match.extra_info:
                    lines.append(f"│  <i>{match.extra_info}</i>")

        if self.ton_address:
            lines.append(f"")
            lines.append(f"📍 <b>Основной:</b> <code>{self.ton_address}</code>")
            lines.append(f"💰 Баланс: <b>{self.ton_balance:.2f} TON</b>")

            # Links
            lines.append(f"🔗 <a href='https://tonviewer.com/{self.ton_address}'>TonViewer</a> • "
                        f"<a href='https://getgems.io/user/{self.ton_address}'>GetGems</a> • "
                        f"<a href='https://dedust.io/portfolio/{self.ton_address}'>DeDust</a>")

            # NFT gifts
            if self.nft_gifts:
                lines.append("")
                nft_word = "ёбаных NFT" if len(self.nft_gifts) > 3 else "NFT"
                lines.append(f"🖼 <b>{len(self.nft_gifts)} {nft_word}</b>")
                for i, nft in enumerate(self.nft_gifts[:5], 1):
                    price_str = f" • {nft.last_sale_price:.2f} TON" if nft.last_sale_price else ""
                    prefix = "└" if i == min(5, len(self.nft_gifts)) else "├"
                    lines.append(f"{prefix} {nft.name}{price_str}")

                if len(self.nft_gifts) > 5:
                    lines.append(f"   <i>...и ещё {len(self.nft_gifts) - 5} штук</i>")

            # GetGems marketplace listings
            if self.getgems_nfts:
                lines.append("")
                lines.append(f"🛒 <b>GETGEMS ЛИСТИНГИ</b>")
                listed = [n for n in self.getgems_nfts if n.sale_price]
                if listed:
                    lines.append(f"📊 На продаже: {len(listed)} шт.")
                    total_val = sum(n.sale_price for n in listed if n.sale_price)
                    lines.append(f"💵 Общая стоимость: {total_val:.2f} TON")
                    for i, nft in enumerate(listed[:5], 1):
                        prefix = "└" if i == min(5, len(listed)) else "├"
                        lines.append(f"{prefix} {nft.name} • {nft.sale_price:.2f} TON")
                    if len(listed) > 5:
                        lines.append(f"   <i>...и ещё {len(listed) - 5}</i>")
                else:
                    lines.append(f"   <i>Ничего не продаёт</i>")

            # NFT history (blockchain transactions)
            if self.nft_history:
                lines.append("")
                lines.append(f"📜 <b>ИСТОРИЯ NFT ДВИЖУХ</b>")

                for i, event in enumerate(self.nft_history[:10], 1):
                    action = event.get("action", "")
                    name = event.get("name", "NFT")
                    ts = event.get("timestamp", 0)

                    from datetime import datetime
                    date_str = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else "?"

                    if action == "transfer":
                        sender = event.get("sender", "")[:8] + "..." if event.get("sender") else "?"
                        recipient = event.get("recipient", "")[:8] + "..." if event.get("recipient") else "?"
                        lines.append(f"├ 📤 {name}")
                        lines.append(f"│  {sender} → {recipient}")
                        lines.append(f"│  {date_str}")
                    elif action == "purchase":
                        price = event.get("price_ton", 0)
                        buyer = event.get("buyer", "")[:8] + "..." if event.get("buyer") else "?"
                        lines.append(f"├ 💰 {name} • {price:.2f} TON")
                        lines.append(f"│  Покупатель: {buyer}")
                        lines.append(f"│  {date_str}")

                if len(self.nft_history) > 10:
                    lines.append(f"└ <i>...и ещё {len(self.nft_history) - 10} транзакций</i>")
        else:
            lines.append(f"   <i>Кошелёк не найден - либо нет, либо не привязан</i>")

        lines.append("")
        lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🔥 <i>Powered by Барыга OSINT</i>")

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

            # Get TON blockchain data - using extended wallet resolver
            wallet_matches = []
            ton_address = None
            ton_balance = 0.0
            nft_gifts = []
            nft_history = []

            try:
                # Try to find wallets through multiple sources
                if profile.username or profile.user_id:
                    logger.info(f"OSINT: Resolving wallets for @{profile.username} / {profile.user_id}")
                    wallet_matches = await wallet_resolver.resolve(
                        username=profile.username,
                        user_id=profile.user_id
                    )
                    logger.info(f"OSINT: Found {len(wallet_matches)} wallet connections")

                    # Use the best match as primary wallet
                    if wallet_matches:
                        ton_address = wallet_matches[0].wallet_address
                        logger.info(f"OSINT: Primary wallet: {ton_address} (source: {wallet_matches[0].source})")

                        # Get wallet info
                        wallet_info = await ton_api.get_wallet_info(ton_address)
                        if wallet_info:
                            ton_balance = wallet_info.balance
                            nft_gifts = wallet_info.gift_nfts
                            logger.info(
                                f"OSINT: TON wallet - balance: {ton_balance:.2f}, "
                                f"NFT gifts: {len(nft_gifts)}"
                            )

                        # Get NFT transaction history
                        logger.info(f"OSINT: Getting NFT history for {ton_address}")
                        raw_events = await ton_api.get_account_nft_history(ton_address, limit=50)
                        if raw_events:
                            parsed, _ = ton_api.parse_nft_events(raw_events)
                            nft_history = parsed
                            logger.info(f"OSINT: Got {len(nft_history)} NFT events")
                    else:
                        logger.info(f"OSINT: No wallet connections found for @{profile.username}")

            except Exception as e:
                logger.warning(f"Failed to get TON data: {e}", exc_info=True)

            # Get GetGems marketplace data
            getgems_nfts = []
            try:
                if ton_address:
                    logger.info(f"OSINT: Getting GetGems NFTs for {ton_address}")
                    getgems_nfts = await getgems_api.get_user_nfts(ton_address, limit=50)
                    logger.info(f"OSINT: Found {len(getgems_nfts)} NFTs on GetGems")
            except Exception as e:
                logger.warning(f"Failed to get GetGems data: {e}", exc_info=True)

            # Calculate GetGems totals
            getgems_listed_count = len([n for n in getgems_nfts if n.sale_price])
            getgems_total_value = None
            if getgems_listed_count > 0:
                getgems_total_value = sum(
                    n.sale_price for n in getgems_nfts
                    if n.sale_price
                )

            return OSINTReport(
                profile=profile,
                gifts_received=gifts_received,
                stats=stats,
                wallet_matches=wallet_matches,
                ton_address=ton_address,
                ton_balance=ton_balance,
                nft_gifts=nft_gifts,
                nft_history=nft_history,
                getgems_nfts=getgems_nfts,
                getgems_listed_count=getgems_listed_count,
                getgems_total_value=getgems_total_value
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
