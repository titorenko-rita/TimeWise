"""Рассылки / JobQueue: мониторинг исполнения отправок."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from db.repositories.job_queue import get_job_card, list_jobs, status_counts
from db.session import get_sessionmaker
from keyboards.job_queue import jobq_detail_menu, jobq_list_menu
from keyboards.panels import panel_by_role
from roles import UserRole
from ui_helpers import clear_temp_messages, safe_edit_text, send_temp_message

logger = logging.getLogger(__name__)
router = Router(name="job_queue_handlers")
_sessionmaker = get_sessionmaker()

PAGE_SIZE = 6


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


def _ru_channel(ch: str) -> str:
    return {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}.get(ch, ch)


def _ru_style(st: str) -> str:
    return {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}.get(st, st)


def _fmt_card(c) -> str:
    who = c.contact_name or "—"
    date = str(c.event_date) if c.event_date else "—"
    retries = c.retry_count if c.retry_count is not None else 0
    parts = [
        "🗓 <b>Рассылки / JobQueue</b>",
        "",
        f"job_id: <code>{c.job_id}</code>",
        f"статус: {_badge(c.status)} <b>{html.escape(_ru_status(c.status))}</b> <code>({html.escape(c.status)})</code>",
        f"попытки: <b>{retries}</b>",
        f"последняя попытка: <code>{html.escape(str(c.last_retry_at) if c.last_retry_at else '—')}</code>",
        f"следующая попытка: <code>{html.escape(str(c.next_retry_at) if c.next_retry_at else '—')}</code>",
        "",
        f"event_id: <code>{c.event_id}</code>",
        f"дата события: <b>{html.escape(date)}</b>",
        f"статус события: <code>{html.escape(c.event_status)}</code>",
        f"канал/стиль: <b>{html.escape(_ru_channel(c.channel))}</b> / <b>{html.escape(_ru_style(c.style))}</b>",
        "",
        f"кому: <b>{html.escape(who)}</b>",
        f"tg_username: <code>{html.escape(c.contact_tg_username or '—')}</code>",
        f"email: <code>{html.escape(c.contact_email or '—')}</code>",
        "",
        f"message_id: <code>{c.message_id or '—'}</code>",
        f"одобрено: <code>{html.escape(str(c.approved_at) if c.approved_at else '—')}</code>",
        f"доставлено: <code>{html.escape(str(c.sent_at) if c.sent_at else '—')}</code>",
    ]
    if c.last_eventlog_status or c.last_eventlog_error:
        parts += [
            "",
            f"последний лог: <code>{html.escape(c.last_eventlog_status or '—')}</code>",
            f"время лога: <code>{html.escape(str(c.last_eventlog_at) if c.last_eventlog_at else '—')}</code>",
        ]
    if c.last_error:
        parts += ["", f"ошибка: {html.escape(c.last_error[:800])}"]
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


@router.callback_query(F.data.in_({"admin:campaigns", "jobq:list"}))
async def jobq_root(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    await _jobq_list(callback, page=0, status=None, role=role)


@router.callback_query(F.data.startswith("jobq:list:"))
async def jobq_list_page(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        return
    try:
        page = int(parts[2])
    except ValueError:
        page = 0
    st = parts[3]
    status = None if st == "all" else st
    await _jobq_list(callback, page=max(page, 0), status=status, role=role)


async def _jobq_list(callback: CallbackQuery, *, page: int, status: str | None, role: UserRole | None) -> None:
    if callback.message is None:
        return
    try:
        async with _sessionmaker() as session:
            items = await list_jobs(
                session,
                limit=PAGE_SIZE + 1,
                offset=page * PAGE_SIZE,
                status=status,
            )
            stats = await status_counts(session)
        has_next = len(items) > PAGE_SIZE
        items = items[:PAGE_SIZE]

        lines = ["🗓 <b>Рассылки / JobQueue</b>", ""]
        if stats:
            lines.append("<b>Статусы</b>")
            for s in stats:
                st_code = str(s.get("status"))
                lines.append(f"- <b>{_ru_status(st_code)}</b> <code>({st_code})</code>: {s.get('c')}")
            lines.append("")
        if status:
            lines.append(f"Показаны задачи: <b>{html.escape(_ru_status(status))}</b> (страница {page + 1}).")
        else:
            lines.append(f"Показаны задачи (страница {page + 1}).")
        text = "\n".join(lines)
        kb = jobq_list_menu(items=items, page=page, has_next=has_next, status=status)
        await clear_temp_messages(callback.message)
        await safe_edit_text(callback.message, text, reply_markup=kb)
    except Exception as e:
        logger.exception("jobq list failed: %s", e)
        await callback.message.answer("😔 Не удалось загрузить JobQueue из БД.", reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("jobq:open:"))
async def jobq_open(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        card = await get_job_card(session, job_id)
    if card is None:
        await callback.message.answer("Задача не найдена.")
        return
    await clear_temp_messages(callback.message)
    await safe_edit_text(callback.message, _fmt_card(card), reply_markup=jobq_detail_menu(job_id))


@router.callback_query(F.data.startswith("jobq:text:"))
async def jobq_show_text(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    async with _sessionmaker() as session:
        card = await get_job_card(session, job_id)
    if card is None:
        await callback.message.answer("Задача не найдена.")
        return
    await _send_long(callback.message, "Текст поздравления (messages.rendered_text)", card.rendered_text)


@router.callback_query(F.data.startswith("jobq:error:"))
async def jobq_show_error(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return
    try:
        job_id = int(callback.data.split(":")[-1])
    except ValueError:
        return
    async with _sessionmaker() as session:
        card = await get_job_card(session, job_id)
    if card is None:
        await callback.message.answer("Задача не найдена.")
        return
    # prefer event_log.error_message; fallback to job_queue.last_error
    err = card.last_eventlog_error or card.last_error
    await _send_long(callback.message, "Причина ошибки", err)

