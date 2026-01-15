#!/usr/bin/env python3
"""Script to authenticate Telegram MTProto session.

Run this once to create a session file that will be used
to fetch gift statistics from Telegram API.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.payments import GetUniqueStarGiftRequest

load_dotenv()


async def main():
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH not set in .env")
        return

    session_path = Path(__file__).parent.parent / "telegram_session"

    print("=" * 50)
    print("Telegram MTProto Authentication")
    print("=" * 50)
    print()
    print(f"API ID: {api_id}")
    print(f"Session will be saved to: {session_path}")
    print()

    client = TelegramClient(str(session_path), api_id, api_hash)

    await client.connect()

    if await client.is_user_authorized():
        print("Already authorized!")
        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username})")
    else:
        print("Not authorized. Starting login process...")
        print()

        phone = input("Enter your phone number (with country code, e.g. +79123456789): ")

        await client.send_code_request(phone)
        print()
        print("Code sent! Check your Telegram app.")
        print()

        code = input("Enter the code you received: ")

        try:
            await client.sign_in(phone, code)
            print()
            print("Successfully logged in!")
        except Exception as e:
            if "Two-steps verification" in str(e) or "password" in str(e).lower():
                print()
                password = input("Enter your 2FA password: ")
                await client.sign_in(password=password)
                print()
                print("Successfully logged in with 2FA!")
            else:
                raise

    # Test the API
    print()
    print("Testing API access...")

    try:
        # Try to fetch a sample gift
        result = await client(GetUniqueStarGiftRequest(slug="tophat-1"))
        if result:
            print("API access confirmed! Can fetch gift statistics.")

            if hasattr(result, 'gift') and result.gift:
                gift = result.gift
                print(f"Sample gift: {gift}")

                if hasattr(gift, 'value') and gift.value:
                    v = gift.value
                    print(f"  Currency: {getattr(v, 'currency', 'N/A')}")
                    print(f"  Floor price: {getattr(v, 'floor_price', 'N/A')}")
                    print(f"  Average price: {getattr(v, 'average_price', 'N/A')}")
                    print(f"  Last sale: {getattr(v, 'last_sale_price', 'N/A')}")

    except Exception as e:
        print(f"Warning: Could not test API: {e}")
        print("But authentication was successful. The session is saved.")

    await client.disconnect()

    print()
    print("=" * 50)
    print("Done! Session saved. You can now use Telegram stats.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
