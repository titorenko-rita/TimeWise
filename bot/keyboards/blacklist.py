"""Клавиатуры для работы с черным списком фраз."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.blacklist import BlacklistRow


def _trim_phrase(phrase: str, *, limit: int = 48) -> str:
    text = " ".join((phrase or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def blacklist_list_menu(
    *,
    items: list[BlacklistRow],
    page: int,
    page_size: int,
    total: int,
    can_manage: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for item in items:
        builder.button(
            text=f"🚫 {_trim_phrase(item.phrase)} (id {item.id})",
            callback_data=f"blacklist:open:{item.id}",
        )

    if can_manage:
        builder.button(text="➕ Добавить фразу", callback_data="blacklist:add")

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"blacklist:list:{page - 1}")
    if (page + 1) * page_size < total:
        nav.button(text="➡️ Вперёд", callback_data=f"blacklist:list:{page + 1}")
    nav.button(text="◀️ Меню", callback_data="nav:user_menu")

    if nav.buttons:
        nav.adjust(2, 1)
        builder.attach(nav)

    builder.adjust(1)
    return builder.as_markup()


def blacklist_detail_menu(*, entry_id: int, can_manage: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_manage:
        builder.button(text="🗑 Удалить", callback_data=f"blacklist:delete:{entry_id}")
    builder.button(text="◀️ К списку", callback_data="blacklist:list:0")
    builder.adjust(1)
    return builder.as_markup()


def blacklist_delete_confirm_menu(entry_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"blacklist:delete_confirm:{entry_id}")
    builder.button(text="❌ Отмена", callback_data=f"blacklist:open:{entry_id}")
    builder.adjust(2)
    return builder.as_markup()
