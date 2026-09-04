"""Общие inline-клавиатуры (пропуск/отмена/меню)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def skip_cancel_menu(*, skip_cb: str, cancel_cb: str = "contacts:cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data=skip_cb)
    builder.button(text="✖️ Отмена", callback_data=cancel_cb)
    builder.adjust(2)
    return builder.as_markup()


def skip_menu(*, skip_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data=skip_cb)
    builder.adjust(1)
    return builder.as_markup()
