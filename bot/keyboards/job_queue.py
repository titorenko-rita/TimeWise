"""Клавиатуры для JobQueue (исполнение рассылок)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.job_queue import JobListItem


STATUSES = ["pending", "retry", "partial", "sent", "failed"]

STATUS_LABELS = {
    "pending": "Ожидают",
    "retry": "Повтор",
    "partial": "Частично",
    "sent": "Отправлено",
    "failed": "Ошибки",
}

CHANNEL_LABELS = {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}


def jobq_list_menu(
    *,
    items: list[JobListItem],
    page: int,
    has_next: bool,
    status: str | None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    def badge(st: str) -> str:
        return {
            "pending": "⏳",
            "retry": "🔁",
            "partial": "🟡",
            "sent": "✅",
            "failed": "⛔",
        }.get(st, "•")

    for it in items:
        date = str(it.event_date) if it.event_date else "—"
        who = it.contact_name or "—"
        retries = it.retry_count if it.retry_count is not None else 0
        err = (it.last_error or "").strip()
        if len(err) > 40:
            err = err[:37] + "..."
        extra = f" • err: {err}" if err else ""
        st_ru = STATUS_LABELS.get(it.status, it.status)
        ch_ru = CHANNEL_LABELS.get(it.channel, it.channel)
        builder.button(
            text=f"{badge(it.status)} {st_ru} • попытки:{retries} • {date} • {who} • {ch_ru}{extra} (id {it.job_id})",
            callback_data=f"jobq:open:{it.job_id}",
        )

    # filters
    filt = InlineKeyboardBuilder()
    filt.button(text="Все", callback_data="jobq:list:0:all")
    for st in STATUSES:
        filt.button(text=STATUS_LABELS.get(st, st), callback_data=f"jobq:list:0:{st}")
    filt.adjust(3, 3)
    builder.attach(filt)

    # nav
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"jobq:list:{page - 1}:{status or 'all'}")
    if has_next:
        nav.button(text="➡️ Вперёд", callback_data=f"jobq:list:{page + 1}:{status or 'all'}")
    nav.button(text="◀️ Меню", callback_data="nav:admin_menu")
    nav.adjust(2, 1)
    builder.attach(nav)

    builder.adjust(1)
    return builder.as_markup()


def jobq_detail_menu(job_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Показать текст", callback_data=f"jobq:text:{job_id}")
    builder.button(text="⚠️ Показать ошибку", callback_data=f"jobq:error:{job_id}")
    builder.button(text="◀️ К списку", callback_data="jobq:list:0:all")
    builder.adjust(2, 1)
    return builder.as_markup()

