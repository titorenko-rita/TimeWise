"""Клавиатуры для экрана Мониторинг."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.monitoring import MonitoringListItem


STATUSES = ["all", "pending", "retry", "failed", "partial", "sent"]
DATES = ["all", "today", "7d"]

STATUS_LABELS = {
    "all": "Все",
    "pending": "Ожидают",
    "retry": "Повтор",
    "failed": "Ошибки",
    "partial": "Частично",
    "sent": "Отправлено",
}

DATE_LABELS = {
    "all": "Все даты",
    "today": "Сегодня",
    "7d": "7 дней",
}

CHANNEL_LABELS = {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}


def monitoring_filters_menu(*, status: str, date: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for st in STATUSES:
        base = STATUS_LABELS.get(st, st)
        label = f"[{base}]" if st == status else base
        builder.button(text=label, callback_data=f"mon:list:0:{st}:{date}")
    builder.adjust(3, 3)
    for d in DATES:
        base = DATE_LABELS.get(d, d)
        label = f"[{base}]" if d == date else base
        builder.button(text=label, callback_data=f"mon:list:0:{status}:{d}")
    builder.adjust(3, 3, 3)
    builder.button(text="◀️ Меню", callback_data="nav:admin_menu")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def monitoring_list_menu(
    *,
    items: list[MonitoringListItem],
    page: int,
    has_next: bool,
    status: str,
    date: str,
    back_cb: str,
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
        who = it.contact_name or "—"
        d = str(it.event_date) if it.event_date else "—"
        appr = "✅" if it.approved_at else ("⏳" if it.approval_status in {"pending", "edited"} else "—")
        sent = "✅" if it.sent_at else "—"
        retries = it.retry_count if it.retry_count is not None else 0
        err = (it.last_error or "").strip()
        if len(err) > 32:
            err = err[:29] + "..."
        extra = f" • err:{err}" if err else ""
        st_ru = STATUS_LABELS.get(it.job_status, it.job_status)
        ch_ru = CHANNEL_LABELS.get(it.channel, it.channel)
        builder.button(
            text=f"{badge(it.job_status)} {st_ru} • попытки:{retries} • {d} • {who} • {ch_ru} • одобр:{appr} дост:{sent}{extra}",
            callback_data=f"mon:open:{it.job_id}",
        )

    # nav
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️ Назад", callback_data=f"mon:list:{page - 1}:{status}:{date}")
    if has_next:
        nav.button(text="➡️ Вперёд", callback_data=f"mon:list:{page + 1}:{status}:{date}")
    nav.button(text="Фильтры", callback_data=f"mon:filters:{status}:{date}")
    nav.button(text="◀️ Меню", callback_data=back_cb)
    nav.adjust(2, 2)
    builder.attach(nav)

    builder.adjust(1)
    return builder.as_markup()


def monitoring_detail_menu(*, job_id: int, can_retry: bool, back_status: str, back_date: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Текст", callback_data=f"mon:text:{job_id}")
    builder.button(text="⚠️ Ошибка", callback_data=f"mon:error:{job_id}")
    if can_retry:
        builder.button(text="🔁 Повторить сейчас", callback_data=f"mon:retry:{job_id}")
    builder.button(text="◀️ Назад", callback_data=f"mon:list:0:{back_status}:{back_date}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()

