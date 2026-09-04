"""Клавиатуры для управления пользователями (таблица Users)."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from roles import UserRole


def admin_users_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить пользователя", callback_data="users:add")
    builder.button(text="⚙️ Управлять пользователем", callback_data="users:manage")
    builder.button(text="📃 Список пользователей", callback_data="users:list")
    builder.button(text="◀️ Назад", callback_data="nav:admin_menu")
    builder.adjust(1)
    return builder.as_markup()


def role_select_menu(tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Admin", callback_data=f"users:set_role:{tg_id}:{UserRole.ADMIN.value}")
    builder.button(
        text="Editor", callback_data=f"users:set_role:{tg_id}:{UserRole.EDITOR.value}"
    )
    builder.button(
        text="Viewer", callback_data=f"users:set_role:{tg_id}:{UserRole.VIEWER.value}"
    )
    builder.button(text="Отмена", callback_data="users:cancel")
    builder.adjust(3, 1)
    return builder.as_markup()


def user_manage_menu(*, tg_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Admin", callback_data=f"users:set_role:{tg_id}:{UserRole.ADMIN.value}")
    builder.button(text="Editor", callback_data=f"users:set_role:{tg_id}:{UserRole.EDITOR.value}")
    builder.button(text="Viewer", callback_data=f"users:set_role:{tg_id}:{UserRole.VIEWER.value}")

    if is_active:
        builder.button(text="⛔ Деактивировать", callback_data=f"users:set_active:{tg_id}:0")
    else:
        builder.button(text="✅ Активировать", callback_data=f"users:set_active:{tg_id}:1")

    builder.button(text="🗑 Удалить (мягко)", callback_data=f"users:delete:{tg_id}")
    builder.button(text="◀️ Назад", callback_data="admin:users")
    builder.adjust(3, 1, 1, 1)
    return builder.as_markup()


def user_delete_confirm_menu(tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"users:delete_confirm:{tg_id}")
    builder.button(text="❌ Отмена", callback_data="admin:users")
    builder.adjust(2)
    return builder.as_markup()

