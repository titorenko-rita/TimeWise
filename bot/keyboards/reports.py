"""Клавиатуры для раздела отчетов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def reports_menu(*, period: str, back_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    def label(key: str, text: str) -> str:
        return f"[{text}]" if key == period else text

    builder.button(text=label("today", "За сегодня"), callback_data="reports:today")
    builder.button(text=label("month", "За месяц"), callback_data="reports:month")
    builder.button(text=label("all", "За все время"), callback_data="reports:all")
    builder.button(text="📥 Скачать CSV", callback_data=f"reports:csv:{period}")
    builder.button(text="📄 Скачать PDF", callback_data=f"reports:pdf:{period}")
    builder.button(text="◀️ Назад в меню", callback_data=back_cb)
    builder.adjust(2, 1, 2, 1)
    return builder.as_markup()

