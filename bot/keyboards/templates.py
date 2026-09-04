"""Клавиатуры для работы с шаблонами (таблица templates)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.templates import TemplateRow


CHANNEL_LABELS = {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}
STYLE_LABELS = {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}
CASE_LABELS = {
    "Nominative": "Именительный",
    "Genitive": "Родительный",
    "Dative": "Дательный",
    "Accusative": "Винительный",
    "Instrumental": "Творительный",
    "Prepositional": "Предложный",
}


def templates_list_menu(*, items: list[TemplateRow], page: int, page_size: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for t in items:
        status = "✅" if t.is_active else "⛔"
        ch = CHANNEL_LABELS.get(t.channel, t.channel)
        st = STYLE_LABELS.get(t.style, t.style)
        cs = CASE_LABELS.get(t.case, t.case)
        builder.button(
            text=f"{status} {t.category} • {ch}/{st} • {cs} • v{t.version} (id {t.id})",
            callback_data=f"templates:open:{t.id}",
        )

    builder.button(text="🔎 Найти по id", callback_data="templates:search")

    nav = InlineKeyboardBuilder()
    prev_page = page - 1
    next_page = page + 1
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"templates:list:{prev_page}")
    if (page + 1) * page_size < total:
        nav.button(text="➡️ Вперёд", callback_data=f"templates:list:{next_page}")
    nav.button(text="◀️ Меню", callback_data="nav:user_menu")

    if nav.buttons:
        nav.adjust(2, 1)
        builder.attach(nav)

    builder.adjust(1)
    return builder.as_markup()


def template_detail_menu(*, template_id: int, is_active: bool, can_edit: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="👁 Предпросмотр", callback_data=f"templates:preview:{template_id}")
    builder.button(text="📚 Версии", callback_data=f"templates:versions:{template_id}")

    if can_edit:
        builder.button(text="✏️ Редактировать текст", callback_data=f"templates:edit:{template_id}")
        builder.button(text="🆕 Новая версия", callback_data=f"templates:new_version:{template_id}")
        if is_active:
            builder.button(text="⛔ Выключить", callback_data=f"templates:active:{template_id}:0")
        else:
            builder.button(text="✅ Включить", callback_data=f"templates:active:{template_id}:1")
        builder.button(text="🗑 Удалить (мягко)", callback_data=f"templates:delete:{template_id}")

    builder.button(text="◀️ К списку", callback_data="templates:list:0")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def template_versions_menu(*, items: list[TemplateRow], current_id: int, can_edit: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in items[:25]:
        marker = "👉" if t.id == current_id else ""
        status = "✅" if t.is_active else "⛔"
        builder.button(
            text=f"{marker}{status} v{t.version} (id {t.id})",
            callback_data=f"templates:open:{t.id}",
        )

    if can_edit:
        builder.button(text="🆕 Новая версия (от текущей)", callback_data=f"templates:new_version:{current_id}")
    builder.button(text="◀️ К списку", callback_data="templates:list:0")
    builder.adjust(2)
    return builder.as_markup()


def template_delete_confirm_menu(template_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"templates:delete_confirm:{template_id}")
    builder.button(text="❌ Отмена", callback_data=f"templates:open:{template_id}")
    builder.adjust(2)
    return builder.as_markup()

