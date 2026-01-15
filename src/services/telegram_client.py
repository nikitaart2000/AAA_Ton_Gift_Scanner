"""Shared Telegram client for services."""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from telethon import TelegramClient

logger = logging.getLogger(__name__)


class TelegramClientManager:
    """Manages shared Telegram client instance with proper locking."""

    def __init__(self):
        self.api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self.session_path = Path(__file__).parent.parent.parent / "telegram_session"

        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()

    async def get_client(self) -> Optional[TelegramClient]:
        """Get connected Telegram client with proper locking.

        Returns:
            Connected TelegramClient or None if not available.
        """
        async with self._lock:
            if self._client and self._client.is_connected():
                return self._client

            if not self.api_id or not self.api_hash:
                logger.error("TELEGRAM_API_ID/HASH not set")
                return None

            try:
                self._client = TelegramClient(
                    str(self.session_path),
                    self.api_id,
                    self.api_hash
                )
                await self._client.connect()

                if not await self._client.is_user_authorized():
                    logger.warning("Telegram session not authorized")
                    return None

                return self._client
            except Exception as e:
                logger.error(f"Failed to connect Telegram: {e}")
                return None

    @property
    def lock(self) -> asyncio.Lock:
        """Get the shared lock for Telegram operations."""
        return self._lock

    async def close(self):
        """Close the Telegram client."""
        async with self._lock:
            if self._client and self._client.is_connected():
                await self._client.disconnect()
                self._client = None


# Global shared instance
tg_client_manager = TelegramClientManager()
