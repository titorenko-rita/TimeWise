"""Обработчики для панели администратора."""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.panels import admin_back_panel, panel_by_role
from roles import UserRole
from db.session import get_sessionmaker
from db.repositories.dashboard import get_status_counts, get_table_counts
from ui_helpers import clear_temp_messages, has_temp_context, reset_temp_context

logger = logging.getLogger(__name__)

router = Router(name="admin_handlers")
_sessionmaker = get_sessionmaker()


ADMIN_HINTS = {
    "admin:campaigns": (
        "🗓 <b>Рассылки и задачи</b>\n\n"
        "Scheduler будет формировать очередь JobQueue по датам. "
        "Отсюда администратор сможет запускать массовые проверки, смотреть статусы: в ожидании / отправлено / ошибка."
    ),
    "admin:monitoring": (
        "📊 <b>Мониторинг</b>\n\n"
        "В финальной версии сюда будут подгружаться метрики из Grafana/Prometheus "
        "— успехи рассылок, время генерации, ретраи."
    ),
    "admin:settings": (
        "⚙️ <b>Настройки</b>\n\n"
        "Секреты, расписание APScheduler, лимиты повторных отправок, управление ролями."
    ),
    "admin:approvals": (
        "✅ <b>Очередь согласования</b>\n\n"
        "Здесь отображаются заявки на согласование перед отправкой, с действиями: одобрить / править / отклонить."
    ),
}


def _fmt_kv(title: str, items: list[tuple[str, str]]) -> str:
    lines = [f"<b>{title}</b>", ""]
    for k, v in items:
        lines.append(f"- <b>{k}</b>: {v}")
    return "\n".join(lines)


@router.callback_query(F.data == "admin:settings")
async def admin_settings(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is None:
        return

    role_note = (
        "Роли Admin/Editor/Viewer берутся из таблицы <code>users</code> (по <code>tg_id</code>). "
        "ADMIN_IDS в .env используется как fallback."
    )
    text = _fmt_kv(
        "⚙️ Настройки (MVP)",
        [
            ("DB_AUTO_CREATE", "вкл" if getattr(__import__('config').settings, "db_auto_create", True) else "выкл"),
            ("Роли", role_note),
        ],
    )

    try:
        await callback.message.edit_text(text, reply_markup=admin_back_panel())
    except Exception:
        await callback.message.answer(text, reply_markup=admin_back_panel())


@router.callback_query(F.data.startswith("admin:"))
async def admin_action_handler(callback: CallbackQuery) -> None:
    """Обработчик действий админ-панели."""
    await callback.answer()

    if callback.message is None:
        logger.warning("callback.message is None for user %s", callback.from_user.id)
        return

    data = callback.data or ""
    text = ADMIN_HINTS.get(
        data,
        "🚧 Функция пока не реализована, но кнопка уже зарезервирована под будущее действие.",
    )

    try:
        await callback.message.edit_text(text, reply_markup=admin_back_panel())
    except Exception as e:
        # Если редактирование не удалось (например, текст не изменился)
        logger.debug("Не удалось отредактировать сообщение: %s", e)
        await callback.message.answer(text, reply_markup=admin_back_panel())


@router.callback_query(F.data == "nav:admin_menu")
async def admin_back_to_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
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
    menu_text = f"{title}\n\nВыберите раздел:"

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
