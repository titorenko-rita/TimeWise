"""Обработчики для панели пользователя."""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.panels import panel_by_role, user_back_panel
from roles import UserRole
from db.session import get_sessionmaker
from db.repositories.dashboard import list_user_events_by_tg_id
from ui_helpers import clear_temp_messages, has_temp_context, reset_temp_context

logger = logging.getLogger(__name__)

router = Router(name="user_handlers")
_sessionmaker = get_sessionmaker()


USER_HINTS = {
    "user:my_events": (
        "🎉 <b>Мои поздравления</b>\n\n"
        "Здесь будет список задач, где вы указаны ответственным: "
        "дни рождения коллег, корпоративные даты."
    ),
    "user:reminders": (
        "🕒 <b>Напоминания</b>\n\n"
        "Лента ближайших событий. В продакшене бот подтянет их из JobQueue "
        "и позволит подтвердить получение."
    ),
    "user:feedback": (
        "📤 <b>Обратная связь</b>\n\n"
        "Скоро появится форма для комментариев о шаблонах и ошибках. "
        "Пока просто напишите администратору в ответ на это сообщение."
    ),
    "user:help": (
        "ℹ️ <b>Помощь</b>\n\n"
        "Если увидели неточность в тексте поздравления — доложите админу. "
        "Система отслеживает ваши ответы и улучшает шаблоны."
    ),
}


@router.callback_query(F.data.startswith("user:"))
async def user_action_handler(callback: CallbackQuery) -> None:
    """Обработчик действий пользовательской панели."""
    await callback.answer()

    if callback.message is None:
        logger.warning("callback.message is None for user %s", callback.from_user.id)
        return

    data = callback.data or ""
    try:
        if data in {"user:my_events", "user:reminders"}:
            async with _sessionmaker() as session:
                rows = await list_user_events_by_tg_id(session, callback.from_user.id, limit=12)
            title = "🎉 <b>Мои поздравления</b>" if data == "user:my_events" else "🕒 <b>Напоминания</b>"
            lines = [title, ""]
            if not rows:
                lines.append("Пока нет событий, где вы назначены ответственным.")
            else:
                for r in rows:
                    who = "—"
                    if r.get("last_name") or r.get("first_name"):
                        who = f"{r.get('last_name') or ''} {r.get('first_name') or ''}".strip()
                    lines.append(
                        f"- <code>{r.get('date')}</code> <code>{r.get('status')}</code> "
                        f"{r.get('channel')}/{r.get('style')} — {who} (ev <code>{r.get('id')}</code>)"
                    )
            text = "\n".join(lines)
        else:
            text = USER_HINTS.get(
                data,
                "🚧 Функция в разработке. Скоро здесь появится интерактивный сценарий."
            )
    except Exception as e:
        logger.exception("User section failed (%s): %s", data, e)
        text = "😔 Не удалось загрузить данные из БД. Проверьте логи и права доступа."

    try:
        await callback.message.edit_text(text, reply_markup=user_back_panel())
    except Exception as e:
        # Если редактирование не удалось
        logger.debug("Не удалось отредактировать сообщение: %s", e)
        await callback.message.answer(text, reply_markup=user_back_panel())


@router.callback_query(F.data == "nav:user_menu")
async def user_back_to_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
    """Возврат в главное меню (по роли)."""
    await callback.answer()

    if callback.message is None:
        return

    if role == UserRole.ADMIN:
        title = "🔧 <b>Панель администратора</b>"
    elif role == UserRole.EDITOR:
        title = "✍️ <b>Панель редактора</b>"
    else:
        title = "👁 <b>Панель просмотра</b>"
    menu_text = f"{title}\n\nВыберите действие:"

    try:
        had_temp_context = has_temp_context(callback.message)
        await clear_temp_messages(callback.message)
        if had_temp_context:
            reset_temp_context(callback.message)
            await callback.message.answer(menu_text, reply_markup=panel_by_role(role or UserRole.VIEWER))
        else:
            await callback.message.edit_text(menu_text, reply_markup=panel_by_role(role or UserRole.VIEWER))
    except Exception as e:
        logger.debug("Не удалось отредактировать сообщение: %s", e)
        reset_temp_context(callback.message)
        await callback.message.answer(menu_text, reply_markup=panel_by_role(role or UserRole.VIEWER))
