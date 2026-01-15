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
    wallets: list[str] = field(default_factory=list)  # For future TON integration
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
        lines.append(f"├ Всего подарков: {self.stats.total_gifts}")
        lines.append(f"├ Общая стоимость: {self.stats.total_stars}⭐️")
        lines.append(f"└ Уникальных отправителей: {self.stats.unique_senders}")

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
        client = await tg_client_manager.get_client()
        if not client:
            return OSINTReport(
                profile=UserProfile(user_id=0),
                error="Telegram client not available"
            )

        try:
            # Resolve user
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
                # Get star gifts for this user
                gifts_result = await client(GetSavedStarGiftsRequest(
                    peer=entity,
                    offset="",
                    limit=100
                ))

                for gift in gifts_result.gifts:
                    # Extract gift info
                    gift_info = self._parse_gift(gift)
                    if gift_info:
                        gifts_received.append(gift_info)
                        stats.add_gift(gift_info)

            except Exception as e:
                logger.warning(f"Failed to get gifts for user: {e}")

            return OSINTReport(
                profile=profile,
                gifts_received=gifts_received,
                stats=stats
            )

        except Exception as e:
            logger.error(f"OSINT lookup failed: {e}", exc_info=True)
            return OSINTReport(
                profile=UserProfile(user_id=0),
                error=str(e)
            )

    def _parse_gift(self, gift) -> Optional[GiftInfo]:
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
                from_user_id = getattr(from_id, 'user_id', None)

            # Check if name is hidden
            name_hidden = getattr(gift, 'name_hidden', False)
            if name_hidden:
                from_name = "Hidden"

            # Get saved/hidden status
            is_saved = not getattr(gift, 'unsaved', True)

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
            logger.warning(f"Failed to parse gift: {e}")
            return None


# Global instance
osint_service = OSINTService()
