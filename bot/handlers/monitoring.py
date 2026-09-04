"""Мониторинг: операционный экран для админа/редактора."""

from __future__ import annotations

import html
import logging
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from db.repositories.monitoring import (
    get_detail,
    list_items,
    retry_now,
    summary,
)
from db.session import get_sessionmaker
from keyboards.monitoring import (
    monitoring_detail_menu,
    monitoring_filters_menu,
    monitoring_list_menu,
)
from keyboards.panels import panel_by_role
from roles import UserRole
from ui_helpers import clear_temp_messages, safe_edit_text, send_temp_message

logger = logging.getLogger(__name__)
router = Router(name="monitoring_handlers")
_sessionmaker = get_sessionmaker()

PAGE_SIZE = 6


def _can_access(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


def _is_admin(role: UserRole | None) -> bool:
    return role == UserRole.ADMIN


def _badge(st: str) -> str:
    return {
        "pending": "⏳",
        "retry": "🔁",
        "partial": "🟡",
        "sent": "✅",
        "failed": "⛔",
    }.get(st, "•")


def _ru_status(st: str | None) -> str:
    return {
        "pending": "в ожидании",
        "retry": "повтор",
        "partial": "частично",
        "sent": "отправлено",
        "failed": "ошибка",
        "all": "все",
        None: "все",
    }.get(st, str(st))


def _ru_period(key: str) -> str:
    return {"all": "все", "today": "сегодня", "7d": "7 дней"}.get(key, key)


def _ru_channel(ch: str) -> str:
    return {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}.get(ch, ch)


def _ru_style(st: str) -> str:
    return {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}.get(st, st)


def _date_filter(d: str) -> tuple[date | None, date | None]:
    today = date.today()
    if d == "today":
        return today, today
    if d == "7d":
        return today - timedelta(days=6), today
    return None, None


def _fmt_summary(s) -> str:
    return (
        "📊 <b>Мониторинг (JobQueue)</b>\n\n"
        f"- ✅ отправлено: <b>{s.sent}</b>\n"
        f"- ⏳ в ожидании: <b>{s.pending}</b>\n"
        f"- 🔁 повтор: <b>{s.retry}</b>\n"
        f"- ⛔ ошибка: <b>{s.failed}</b>\n"
        f"- 🟡 частично: <b>{s.partial}</b>\n"
    )


def _fmt_detail(d) -> str:
    who = d.contact_name or "—"
    dt = str(d.event_date) if d.event_date else "—"
    retries = d.retry_count if d.retry_count is not None else 0
    resp = f"<code>{d.responsible_tg_id}</code>" if d.responsible_tg_id else "—"
    appr = html.escape(str(d.approved_at)) if d.approved_at else "—"
    sent = html.escape(str(d.sent_at)) if d.sent_at else "—"
    parts = [
        "📌 <b>Детали задачи</b>",
        "",
        f"job_id: <code>{d.job_id}</code>",
        f"статус: {_badge(d.job_status)} <b>{html.escape(_ru_status(d.job_status))}</b> <code>({html.escape(d.job_status)})</code>",
        f"попытки: <b>{retries}</b>",
        f"последняя попытка: <code>{html.escape(str(d.last_retry_at) if d.last_retry_at else '—')}</code>",
        f"следующая попытка: <code>{html.escape(str(d.next_retry_at) if d.next_retry_at else '—')}</code>",
        "",
        f"event_id: <code>{d.event_id}</code>",
        f"дата события: <b>{html.escape(dt)}</b>",
        f"статус события: <code>{html.escape(d.event_status)}</code>",
        f"канал/стиль: <b>{html.escape(_ru_channel(d.channel))}</b> / <b>{html.escape(_ru_style(d.style))}</b>",
        f"ответственный (tg_id): {resp}",
        "",
        f"кому: <b>{html.escape(who)}</b>",
        f"tg_username: <code>{html.escape(d.contact_tg_username or '—')}</code>",
        f"email: <code>{html.escape(d.contact_email or '—')}</code>",
        "",
        f"согласование: <code>{html.escape(d.approval_status or '—')}</code>",
        f"одобрено: <code>{appr}</code>",
        f"отправлено: <code>{sent}</code>",
    ]
    if d.last_eventlog_status or d.last_eventlog_error:
        parts += [
            "",
            f"последний лог: <code>{html.escape(d.last_eventlog_status or '—')}</code>",
            f"время лога: <code>{html.escape(str(d.last_eventlog_at) if d.last_eventlog_at else '—')}</code>",
        ]
    if d.last_error:
        parts += ["", f"ошибка: {html.escape(d.last_error[:800])}"]
    return "\n".join(parts)


async def _send_long(message: Message, title: str, text: str | None) -> None:
    t = (text or "").strip()
    if not t:
        await send_temp_message(message, f"<b>{title}</b>\n<i>(пусто)</i>")
        return
    escaped = html.escape(t)
    chunk_size = 3500
    chunks = [escaped[i : i + chunk_size] for i in range(0, len(escaped), chunk_size)]
    await send_temp_message(message, f"<b>{title}</b>")
    for i, c in enumerate(chunks[:6]):
        prefix = "" if i == 0 else f"<b>Продолжение {i + 1}</b>\n"
        await send_temp_message(message, prefix + f"<pre>{c}</pre>")
    if len(chunks) > 6:
        await send_temp_message(message, "…показана только часть.")


@router.callback_query(F.data == "admin:monitoring")
async def monitoring_root(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    # default view: problematic + 7d
    await _monitoring_list(callback, page=0, status="failed", date_key="7d", role=role, actor_user_id=actor_user_id)


@router.callback_query(F.data.startswith("mon:filters:"))
async def monitoring_filters(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        return
    status = parts[2]
    date_key = parts[3]
    await callback.message.edit_text(
        "⚙️ <b>Фильтры мониторинга</b>\n\nВыберите статус и период:",
        reply_markup=monitoring_filters_menu(status=status, date=date_key),
    )


@router.callback_query(F.data.startswith("mon:list:"))
async def monitoring_list(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.data is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 5:
        return
    try:
        page = int(parts[2])
    except ValueError:
        page = 0
    status = parts[3]
    date_key = parts[4]
    await _monitoring_list(
        callback,
        page=max(page, 0),
        status=status,
        date_key=date_key,
        role=role,
        actor_user_id=actor_user_id,
    )


async def _monitoring_list(
    callback: CallbackQuery,
    *,
    page: int,
    status: str,
    date_key: str,
    role: UserRole | None,
    actor_user_id: int | None,
) -> None:
    if callback.message is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    date_from, date_to = _date_filter(date_key)
    st = None if status == "all" else status
    try:
        async with _sessionmaker() as session:
            responsible = None if _is_admin(role) else actor_user_id
            s = await summary(session, responsible_user_id=responsible)
            items = await list_items(
                session,
                responsible_user_id=responsible,
                status=st,
                date_from=date_from,
                date_to=date_to,
                limit=PAGE_SIZE + 1,
                offset=page * PAGE_SIZE,
            )
        has_next = len(items) > PAGE_SIZE
        items = items[:PAGE_SIZE]

        head = _fmt_summary(s)
        scope = "все задачи" if _is_admin(role) else "только мои задачи"
        flt = f"фильтр: <code>{html.escape(_ru_status(status))}</code>, период: <code>{html.escape(_ru_period(date_key))}</code>"
        text = f"{head}\n<b>Список</b> ({scope})\n{flt}\nстраница: <b>{page + 1}</b>"
        kb = monitoring_list_menu(
            items=items,
            page=page,
            has_next=has_next,
            status=status,
            date=date_key,
            back_cb="nav:admin_menu" if role == UserRole.ADMIN else "nav:user_menu",
        )
        await clear_temp_messages(callback.message)
        await safe_edit_text(callback.message, text, reply_markup=kb)
    except Exception as e:
        logger.exception("monitoring list failed: %s", e)
        await callback.message.answer("😔 Не удалось загрузить мониторинг из БД.", reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("mon:open:"))
async def monitoring_open(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    # defaults for back; list buttons always use mon:list; we keep simple
    back_status, back_date = "all", "7d"
    async with _sessionmaker() as session:
        responsible = None if _is_admin(role) else actor_user_id
        d = await get_detail(session, job_id=job_id, responsible_user_id=responsible)
    if d is None:
        await callback.message.answer("Задача не найдена.")
        return
    can_retry = _is_admin(role) and d.job_status in {"failed", "retry", "partial", "pending"}
    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _fmt_detail(d),
        reply_markup=monitoring_detail_menu(job_id=job_id, can_retry=can_retry, back_status=back_status, back_date=back_date),
    )


@router.callback_query(F.data.startswith("mon:text:"))
async def monitoring_text(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    async with _sessionmaker() as session:
        responsible = None if _is_admin(role) else actor_user_id
        d = await get_detail(session, job_id=job_id, responsible_user_id=responsible)
    if d is None:
        await callback.message.answer("Задача не найдена.")
        return
    await _send_long(callback.message, "Текст сообщения (messages.rendered_text)", d.rendered_text)


@router.callback_query(F.data.startswith("mon:error:"))
async def monitoring_error(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    async with _sessionmaker() as session:
        responsible = None if _is_admin(role) else actor_user_id
        d = await get_detail(session, job_id=job_id, responsible_user_id=responsible)
    if d is None:
        await callback.message.answer("Задача не найдена.")
        return
    err = d.last_eventlog_error or d.last_error
    await _send_long(callback.message, "Ошибка (event_log.error_message / job_queue.last_error)", err)


@router.callback_query(F.data.startswith("mon:retry:"))
async def monitoring_retry(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if role != UserRole.ADMIN:
        await callback.answer("⛔ Доступ только для Admin.", show_alert=True)
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    async with _sessionmaker() as session:
        ok, msg = await retry_now(
            session,
            job_id=job_id,
            responsible_user_id=None,
            actor_user_id=actor_user_id,
        )
    await send_temp_message(callback.message, msg, reply_markup=panel_by_role(role or UserRole.VIEWER))

