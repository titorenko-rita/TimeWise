"""Клавиатуры для ApprovalQueue."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.approvals import ApprovalListItem


STATUS_LABELS = {
    "pending": "На согласовании",
    "edited": "Правки внесены",
    "approved": "Одобрено",
    "rejected": "Отклонено",
}

CHANNEL_LABELS = {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}
STYLE_LABELS = {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}


def approvals_list_menu(
    *,
    items: list[ApprovalListItem],
    page: int,
    has_next: bool,
    can_batch: bool,
    event_kind: str = "all",
    back_cb: str = "nav:admin_menu",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    def badge(status: str) -> str:
        return {
            "pending": "⏳",
            "edited": "✏️",
            "approved": "✅",
            "rejected": "⛔",
        }.get(status, "•")

    for it in items:
        who = it.contact_name or "—"
        date = str(it.event_date) if it.event_date else "—"
        ch = it.channel or "—"
        st = it.style or "—"
        kind_icon = "🎂" if it.holiday_id is None else "🎉"
        st_ru = STATUS_LABELS.get(it.status, it.status)
        ch_ru = CHANNEL_LABELS.get(ch, ch)
        style_ru = STYLE_LABELS.get(st, st)
        builder.button(
            text=f"{badge(it.status)} {kind_icon} {st_ru} • {date} • {who} • {ch_ru}/{style_ru} (id {it.approval_id})",
            callback_data=f"approvals:open:{it.approval_id}:{event_kind}",
        )

    filters = InlineKeyboardBuilder()
    filters.button(text="📋 Все", callback_data="approvals:list:0:all")
    filters.button(text="🎂 Дни рождения", callback_data="approvals:list:0:birthday")
    filters.button(text="🎉 Другие праздники", callback_data="approvals:list:0:holiday")
    filters.adjust(1)
    builder.attach(filters)

    if can_batch:
        batch = InlineKeyboardBuilder()
        batch.button(text="✏️ Править пачку за сегодня", callback_data=f"approvals:batch_edit_today:{event_kind}")
        batch.button(text="✅ Одобрить всё за сегодня", callback_data=f"approvals:batch_approve_today:{event_kind}")
        batch.button(text="⛔ Отклонить всё за сегодня", callback_data=f"approvals:batch_reject_today:{event_kind}")
        batch.adjust(1)
        builder.attach(batch)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"approvals:list:{page - 1}:{event_kind}")
    if has_next:
        nav.button(text="➡️ Вперёд", callback_data=f"approvals:list:{page + 1}:{event_kind}")
    nav.button(text="◀️ Меню", callback_data=back_cb)
    nav.adjust(2, 1)
    builder.attach(nav)

    builder.adjust(1)
    return builder.as_markup()


def approval_detail_menu(
    *,
    approval_id: int,
    can_act: bool,
    event_kind: str = "all",
    batch_mode: bool = False,
    prev_approval_id: int | None = None,
    next_approval_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    approve_cb = (
        f"approvals:batch_approve:{approval_id}:{event_kind}"
        if batch_mode
        else f"approvals:approve:{approval_id}:{event_kind}"
    )
    edit_cb = (
        f"approvals:batch_edit:{approval_id}:{event_kind}"
        if batch_mode
        else f"approvals:edit:{approval_id}:{event_kind}"
    )
    reject_cb = (
        f"approvals:batch_reject:{approval_id}:{event_kind}"
        if batch_mode
        else f"approvals:reject:{approval_id}:{event_kind}"
    )
    if can_act:
        builder.button(text="✅ Одобрить", callback_data=approve_cb)
        builder.button(text="✏️ Править", callback_data=edit_cb)
        builder.button(text="⛔ Отменить", callback_data=reject_cb)
    if batch_mode:
        if prev_approval_id is not None:
            builder.button(text="⬅️ Предыдущая", callback_data=f"approvals:batch_open:{prev_approval_id}:{event_kind}")
        if next_approval_id is not None:
            builder.button(text="➡️ Следующая", callback_data=f"approvals:batch_open:{next_approval_id}:{event_kind}")
    builder.button(text="◀️ К списку", callback_data=f"approvals:list:0:{event_kind}")
    builder.adjust(3, 2, 1)
    return builder.as_markup()
