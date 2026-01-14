"""Keyboard layouts for the bot."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """Get main menu keyboard."""
    buttons = [
        [KeyboardButton(text="📊 Stats")],
        [KeyboardButton(text="⭐ Watchlist"), KeyboardButton(text="🔇 Muted")],
        [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="❓ Help")],
    ]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Get settings inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="🎯 Mode: Spam", callback_data="settings:mode"),
            InlineKeyboardButton(text="💰 Profit: 12%", callback_data="settings:profit"),
        ],
        [
            InlineKeyboardButton(
                text="🎨 Background: Any", callback_data="settings:background"
            ),
        ],
        [
            InlineKeyboardButton(text="💎 Price Range", callback_data="settings:price"),
        ],
        [InlineKeyboardButton(text="✅ Done", callback_data="settings:done")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)
