from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from roles import UserRole


def holidays_menu(role: UserRole | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить праздник", callback_data="holidays:add")
    back = "nav:admin_menu" if role == UserRole.ADMIN else "nav:user_menu"
    builder.button(text="◀️ Меню", callback_data=back)
    builder.adjust(1)
    return builder.as_markup()


def holiday_gender_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Любой", callback_data="holidays:gender:any")
    builder.button(text="М", callback_data="holidays:gender:Male")
    builder.button(text="Ж", callback_data="holidays:gender:Female")
    builder.adjust(1, 2)
    return builder.as_markup()
