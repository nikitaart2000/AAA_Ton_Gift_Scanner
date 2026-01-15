"""Quick test for Telegram stats."""

import asyncio
import os
import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv
load_dotenv()

from telethon import TelegramClient
from telethon.tl.functions.payments import GetUniqueStarGiftRequest
from telethon.tl import functions


async def main():
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    session_path = Path(__file__).parent / "telegram_session"

    print(f"Connecting with session: {session_path}")

    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("Not authorized!")
        return

    print("Connected! Testing gift stats...")
    print()

    # Test with a few different slugs
    test_slugs = ["tophat-1", "icecream-1000", "lunarsnake-5000"]

    for slug in test_slugs:
        print(f"=== {slug} ===")
        try:
            # First get basic gift info
            result = await client(GetUniqueStarGiftRequest(slug=slug))

            if result and result.gift:
                gift = result.gift
                print(f"  Title: {gift.title}")
                print(f"  Value: {gift.value_amount / 100} {gift.value_currency}")

            # Try to get value info (floor, average, etc.)
            try:
                from telethon.tl.functions.payments import GetUniqueStarGiftValueInfoRequest

                value_info = await client(GetUniqueStarGiftValueInfoRequest(slug=slug))

                print(f"  Value Info type: {type(value_info).__name__}")
                for attr in dir(value_info):
                    if not attr.startswith('_') and not attr.startswith('CONSTRUCTOR'):
                        val = getattr(value_info, attr, None)
                        if val is not None and not callable(val):
                            print(f"  {attr}: {val}")

            except Exception as e2:
                print(f"  GetUniqueStarGiftValueInfoRequest error: {e2}")

        except Exception as e:
            print(f"  Error: {e}")

        print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
