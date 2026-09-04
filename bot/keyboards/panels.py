"""Inline-клавиатуры для ролевых панелей."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from roles import UserRole


def admin_panel() -> InlineKeyboardMarkup:
    """Главная панель администратора."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📇 Контакты", callback_data="admin:contacts")
    builder.button(text="🎉 Праздники", callback_data="admin:holidays")
    builder.button(text="🗓 Рассылки", callback_data="admin:campaigns")
    builder.button(text="📝 Шаблоны", callback_data="admin:templates")
    builder.button(text="🚫 Чёрный список", callback_data="admin:blacklist")
    builder.button(text="📊 Мониторинг", callback_data="admin:monitoring")
    builder.button(text="📑 Отчёты", callback_data="reports:root")
    builder.button(text="👥 Пользователи", callback_data="admin:users")
    builder.button(text="⚙️ Настройки", callback_data="admin:settings")
    builder.button(text="✅ Approval", callback_data="admin:approvals")
    builder.adjust(2)
    return builder.as_markup()


def editor_panel() -> InlineKeyboardMarkup:
    """Главная панель редактора."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📇 Контакты", callback_data="admin:contacts")
    builder.button(text="🎉 Праздники", callback_data="admin:holidays")
    builder.button(text="📝 Шаблоны", callback_data="admin:templates")
    builder.button(text="🚫 Чёрный список", callback_data="admin:blacklist")
    builder.button(text="✅ Approval", callback_data="admin:approvals")
    builder.button(text="📊 Мониторинг", callback_data="admin:monitoring")
    builder.button(text="📑 Отчёты", callback_data="reports:root")
    builder.button(text="ℹ️ Помощь", callback_data="user:help")
    builder.adjust(2)
    return builder.as_markup()


def viewer_panel() -> InlineKeyboardMarkup:
    """Главная панель просмотра."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Отчёты", callback_data="reports:root")
    builder.button(text="📈 Статистика", callback_data="viewer:stats")
    builder.button(text="📅 События", callback_data="viewer:events")
    builder.button(text="✉️ Сообщения", callback_data="viewer:messages")
    builder.button(text="📝 Шаблоны", callback_data="templates:list")
    builder.button(text="ℹ️ Помощь", callback_data="user:help")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def admin_back_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в меню", callback_data="nav:admin_menu")
    return builder.as_markup()


def user_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎉 Мои поздравления", callback_data="user:my_events")
    builder.button(text="🕒 Напоминания", callback_data="user:reminders")
    builder.button(text="📤 Отправить отзыв", callback_data="user:feedback")
    builder.button(text="ℹ️ Помощь", callback_data="user:help")
    builder.adjust(2)
    return builder.as_markup()


def user_back_panel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в меню", callback_data="nav:user_menu")
    return builder.as_markup()


def panel_by_role(role: UserRole) -> InlineKeyboardMarkup:
    if role == UserRole.ADMIN:
        return admin_panel()
    if role == UserRole.EDITOR:
        return editor_panel()
    return viewer_panel()
