"""Обработчик ошибок для бота."""

import logging
from typing import Any

from aiogram import Router
from aiogram.types import ErrorEvent

from config import settings
from db.repositories.users import get_by_tg_id
from db.session import get_sessionmaker
from observability import record_handler_error
from roles import UserRole, resolve_role

logger = logging.getLogger(__name__)

router = Router(name="error_handlers")
_sessionmaker = get_sessionmaker()


async def _resolve_error_role(event: ErrorEvent, kwargs: dict[str, Any]) -> UserRole | None:
    role: UserRole | None = kwargs.get("role")
    if role is not None:
        return role

    tg_id: int | None = None
    update = event.update
    if update and update.callback_query and update.callback_query.from_user:
        tg_id = update.callback_query.from_user.id
    elif update and update.message and update.message.from_user:
        tg_id = update.message.from_user.id

    if tg_id is None:
        return None

    try:
        async with _sessionmaker() as session:
            db_user = await get_by_tg_id(session, tg_id)
        if db_user and db_user.is_active:
            return UserRole.from_value(db_user.role)
    except Exception:
        return resolve_role(tg_id, settings.admin_ids)

    return resolve_role(tg_id, settings.admin_ids)


@router.error()
async def error_handler(event: ErrorEvent, **kwargs: Any) -> bool:
    """
    Глобальный обработчик ошибок.
    Логирует ошибку и пытается уведомить пользователя.
    """
    record_handler_error("bot")
    logger.exception(
        "Ошибка при обработке update %s: %s",
        event.update.update_id if event.update else "unknown",
        event.exception,
    )

    # Пытаемся уведомить пользователя
    update = event.update
    error_message = "😔 Произошла ошибка. Попробуйте позже или обратитесь к администратору."
    try:
        if update.callback_query:
            await update.callback_query.answer(
                "Произошла ошибка. Попробуйте ещё раз.",
                show_alert=True,
            )
            if update.callback_query.message:
                await update.callback_query.message.answer(error_message)
        elif update.message:
            await update.message.answer(error_message)
    except Exception as notify_error:
        logger.error("Не удалось уведомить пользователя об ошибке: %s", notify_error)

    return True  # Ошибка обработана
