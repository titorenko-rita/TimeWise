"""Middleware для логирования действий пользователей."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from observability import record_update

logger = logging.getLogger(__name__)
MAX_LOG_TEXT_LEN = 160


def _truncate(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= MAX_LOG_TEXT_LEN:
        return normalized
    return normalized[: MAX_LOG_TEXT_LEN - 1] + "…"


class LoggingMiddleware(BaseMiddleware):
    """Логирует все входящие сообщения и callback-запросы."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        action = "unknown"

        if isinstance(event, Message):
            user = event.from_user
            action = f"message: {_truncate(event.text or '<media>')}"
            record_update("message")
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            action = f"callback: {_truncate(event.data or 'unknown')}"
            record_update("callback")

        if user:
            logger.info(
                "User [%s] @%s (id=%d) → %s",
                user.full_name,
                user.username or "no_username",
                user.id,
                action,
            )

        return await handler(event, data)

