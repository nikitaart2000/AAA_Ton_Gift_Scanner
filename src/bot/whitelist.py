"""
Whitelist для ограничения доступа к боту
"""
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable, Union

logger = logging.getLogger(__name__)

# Whitelist пользователей (Telegram User IDs)
ALLOWED_USERS = [
    975050021,  # @runstitchrun (nikita)
    963293176,  # @danfz (Dan)
]

# Режим: если True, пропускает всех (для первоначальной настройки)
# После получения User ID установите в False
WHITELIST_DISABLED = False  # ✅ ENABLED - only whitelisted users can access


class WhitelistMiddleware(BaseMiddleware):
    """Middleware для проверки whitelist пользователей."""

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any],
    ) -> Any:
        # Получаем user из события
        user = event.from_user

        if not user:
            logger.warning("❌ Событие без пользователя")
            return

        # Логируем все попытки доступа
        logger.info(f"📝 User trying to access bot: ID={user.id}, username=@{user.username}, name={user.full_name}")

        # Если whitelist отключён, пропускаем всех
        if WHITELIST_DISABLED:
            logger.info(f"✅ Whitelist disabled - allowing user {user.id}")
            return await handler(event, data)

        # Проверяем whitelist
        if user.id in ALLOWED_USERS:
            logger.info(f"✅ User {user.id} (@{user.username}) is whitelisted")
            return await handler(event, data)
        else:
            logger.warning(f"❌ User {user.id} (@{user.username}) is NOT whitelisted - blocking access")

            # Отправляем сообщение о блокировке
            if isinstance(event, Message):
                await event.answer(
                    "⛔ Доступ запрещён.\n\n"
                    "Этот бот доступен только для авторизованных пользователей.\n"
                    f"Ваш User ID: {user.id}"
                )

            # Не вызываем handler - блокируем доступ
            return
