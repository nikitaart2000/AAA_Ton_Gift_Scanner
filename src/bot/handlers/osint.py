"""OSINT lookup command handler."""

import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.services.osint import osint_service

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("lookup", "osint", "whois"))
async def cmd_lookup(message: Message):
    """
    Handle /lookup command for OSINT user analysis.

    Usage:
        /lookup @username
        /lookup 123456789
    """
    # Parse argument
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.reply(
            "🔍 <b>OSINT Lookup</b>\n\n"
            "Использование:\n"
            "<code>/lookup @username</code>\n"
            "<code>/lookup user_id</code>\n\n"
            "Пример:\n"
            "<code>/lookup @durov</code>",
            parse_mode="HTML"
        )
        return

    target = args[1].strip()

    # Send initial message
    status_msg = await message.reply(
        f"🔍 Ищу информацию о <code>{target}</code>...",
        parse_mode="HTML"
    )

    try:
        # Perform lookup
        logger.info(f"Handler: Starting lookup for {target}")
        report = await osint_service.lookup_user(target)
        logger.info(f"Handler: Got report, error={report.error}")

        if report.error:
            logger.info(f"Handler: Sending error message: {report.error}")
            await status_msg.edit_text(
                f"❌ Ошибка: {report.error}",
                parse_mode="HTML"
            )
            logger.info("Handler: Error message sent")
            return

        # Format and send report
        report_text = report.format_telegram_message()
        logger.info(f"Handler: Sending report ({len(report_text)} chars)")

        await status_msg.edit_text(
            report_text,
            parse_mode="HTML"
        )

        logger.info(
            f"OSINT lookup by {message.from_user.id} for {target}: "
            f"{report.stats.total_gifts} gifts found"
        )

    except Exception as e:
        logger.error(f"OSINT lookup failed: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Ошибка при поиске: {str(e)}",
            parse_mode="HTML"
        )
