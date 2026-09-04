"""Клавиатуры для управления контактами (таблица Contacts)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from roles import UserRole


def admin_contacts_menu(role: UserRole | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить контакт", callback_data="contacts:add")
    builder.button(text="📥 Импорт CSV/Excel", callback_data="contacts:import")
    builder.button(text="📃 Список контактов", callback_data="contacts:list")
    builder.button(text="✏️ Редактировать контакт", callback_data="contacts:edit")
    if role == UserRole.ADMIN:
        builder.button(text="🗑 Удалить контакт", callback_data="contacts:delete")
    back = "nav:admin_menu" if role == UserRole.ADMIN else "nav:user_menu"
    builder.button(text="◀️ Назад", callback_data=back)
    builder.adjust(1)
    return builder.as_markup()


def contacts_list_actions_menu(*, has_filters: bool, role: UserRole | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔎 Поиск по ФИО", callback_data="contacts:list_filter:fio")
    builder.button(text="🏢 По компании", callback_data="contacts:list_filter:company")
    builder.button(text="💼 По должности", callback_data="contacts:list_filter:position")
    if has_filters:
        builder.button(text="♻️ Сбросить фильтры", callback_data="contacts:list_reset")
    builder.button(text="◀️ Назад", callback_data="contacts:cancel")
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()


def gender_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="М", callback_data="contacts:gender:Male")
    builder.button(text="Ж", callback_data="contacts:gender:Female")
    builder.adjust(2)
    return builder.as_markup()


def preferred_channel_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Telegram", callback_data="contacts:channel:Telegram")
    builder.button(text="Email", callback_data="contacts:channel:Email")
    builder.adjust(2)
    return builder.as_markup()


def default_style_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Дружеский", callback_data="contacts:style:Friendly")
    builder.button(text="Деловой", callback_data="contacts:style:Business")
    builder.button(text="Официальный", callback_data="contacts:style:Official")
    builder.adjust(2, 1)
    return builder.as_markup()


def preferred_channel_edit_menu(contact_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # contacts:edit_channel:<contact_id>:<value>
    builder.button(text="Telegram", callback_data=f"contacts:edit_channel:{contact_id}:Telegram")
    builder.button(text="Email", callback_data=f"contacts:edit_channel:{contact_id}:Email")
    builder.button(text="Отмена", callback_data="contacts:cancel")
    builder.adjust(2, 1)
    return builder.as_markup()


def default_style_edit_menu(contact_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # contacts:edit_style:<contact_id>:<value>
    builder.button(text="Дружеский", callback_data=f"contacts:edit_style:{contact_id}:Friendly")
    builder.button(text="Деловой", callback_data=f"contacts:edit_style:{contact_id}:Business")
    builder.button(text="Официальный", callback_data=f"contacts:edit_style:{contact_id}:Official")
    builder.button(text="Отмена", callback_data="contacts:cancel")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def contact_edit_fields_menu(contact_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # contacts:edit_field:<contact_id>:<field>
    builder.button(text="Фамилия", callback_data=f"contacts:edit_field:{contact_id}:last_name")
    builder.button(text="Имя", callback_data=f"contacts:edit_field:{contact_id}:first_name")
    builder.button(text="Отчество", callback_data=f"contacts:edit_field:{contact_id}:middle_name")
    builder.button(text="ДР", callback_data=f"contacts:edit_field:{contact_id}:birthday")
    builder.button(text="Часовой пояс", callback_data=f"contacts:edit_field:{contact_id}:tz")
    builder.button(text="tg_username", callback_data=f"contacts:edit_field:{contact_id}:tg_username")
    builder.button(text="tg_chat_id", callback_data=f"contacts:edit_field:{contact_id}:tg_chat_id")
    builder.button(text="email", callback_data=f"contacts:edit_field:{contact_id}:email")
    builder.button(text="Канал", callback_data=f"contacts:edit_field:{contact_id}:preferred_channel")
    builder.button(text="Стиль", callback_data=f"contacts:edit_field:{contact_id}:default_style")
    builder.button(text="Сегмент", callback_data=f"contacts:edit_field:{contact_id}:segment")
    builder.button(text="Заметка", callback_data=f"contacts:edit_field:{contact_id}:notes")
    builder.button(text="Активность", callback_data=f"contacts:edit_field:{contact_id}:is_active")
    builder.button(text="Отмена", callback_data="contacts:cancel")
    builder.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def contact_delete_confirm_menu(contact_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"contacts:delete_confirm:{contact_id}")
    builder.button(text="❌ Отмена", callback_data="contacts:cancel")
    builder.adjust(1)
    return builder.as_markup()


def contact_active_menu(contact_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Активен", callback_data=f"contacts:set_active:{contact_id}:1")
    builder.button(text="Не активен", callback_data=f"contacts:set_active:{contact_id}:0")
    builder.button(text="Отмена", callback_data="contacts:cancel")
    builder.adjust(2, 1)
    return builder.as_markup()
