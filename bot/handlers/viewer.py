"""Обработчики для панели Viewer (только просмотр)."""

import csv
import io
import logging
import os
import textwrap

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from db.repositories.dashboard import get_status_counts, get_table_counts, list_events, list_messages
from db.repositories.reports import get_report_registry, get_report_summary
from roles import UserRole
from db.session import get_sessionmaker
from keyboards.panels import user_back_panel
from keyboards.reports import reports_menu
from ui_helpers import clear_temp_messages, safe_edit_text

logger = logging.getLogger(__name__)

router = Router(name="viewer_handlers")
_sessionmaker = get_sessionmaker()

VIEWER_HINTS = {
    "viewer:reports": (
        "📊 <b>Отчёты</b>\n\n"
        "Здесь будет выгрузка реестров рассылок (PDF/CSV) и сводные отчёты."
    ),
    "viewer:stats": (
        "📈 <b>Статистика</b>\n\n"
        "Здесь будет краткая сводка (аналог /stats): отправлено, ошибки, ретраи, время генерации."
    ),
    "viewer:events": (
        "📅 <b>События</b>\n\n"
        "Здесь будет список событий (Events) со статусами, без возможности approve/редактирования."
    ),
    "viewer:messages": (
        "✉️ <b>Сообщения</b>\n\n"
        "Здесь будет список сообщений (Messages) и статусов отправки, только просмотр."
    ),
}


def _is_viewer(role: UserRole | None) -> bool:
    return role == UserRole.VIEWER


def _can_access_reports(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR, UserRole.VIEWER}


def _reports_back_cb(role: UserRole | None) -> str:
    return "nav:admin_menu" if role == UserRole.ADMIN else "nav:user_menu"


def _period_label(period: str) -> str:
    return {"today": "сегодня", "month": "текущий месяц", "all": "все время"}.get(period, period)


def _register_pdf_font() -> str:
    for font_name, font_path in [
        ("TimeWiseArial", r"C:\Windows\Fonts\arial.ttf"),
        ("TimeWiseDejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("TimeWiseDejaVu", "/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    ]:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                return font_name
            except Exception:
                continue
    return "Helvetica"


def _build_report_text(period: str, summary) -> str:
    return "\n".join(
        [
            "📊 <b>Отчёты</b>",
            "",
            f"Период: <b>{_period_label(period)}</b>",
            "",
            "<b>Сводка по рассылкам</b>",
            f"- Всего событий: <b>{summary.total_events}</b>",
            f"- Одобрено: <b>{summary.approved_messages}</b>",
            f"- На согласовании: <b>{summary.pending_approvals}</b>",
            f"- Отклонено: <b>{summary.rejected_approvals}</b>",
            f"- Отправлено: <b>{summary.sent_messages}</b>",
            f"- Ошибок: <b>{summary.failed_jobs}</b>",
            f"- С ретраями: <b>{summary.retried_jobs}</b>",
            "",
            "<b>Качество и скорость</b>",
            f"- Успешность доставки: <b>{summary.success_rate_pct:.1f}%</b>",
            f"- Доля ошибок: <b>{summary.error_rate_pct:.1f}%</b>",
            f"- Среднее время подготовки: <b>{summary.avg_generation_ms} мс</b>",
            f"- Среднее время доставки: <b>{summary.avg_delivery_ms} мс</b>",
            "",
            "Выгрузка реестра доступна кнопкой ниже в формате CSV.",
        ]
    )


def _build_stats_text(summary) -> str:
    return "\n".join(
        [
            "📊 <b>Статистика TimeWise за сегодня</b>",
            "",
            f"Всего событий: <b>{summary.total_events}</b>",
            f"Одобрено: <b>{summary.approved_messages}</b>",
            f"На согласовании: <b>{summary.pending_approvals}</b>",
            f"Отклонено: <b>{summary.rejected_approvals}</b>",
            f"Отправлено: <b>{summary.sent_messages}</b>",
            f"Ошибок: <b>{summary.failed_jobs}</b>",
            f"Ретраев: <b>{summary.retried_jobs}</b>",
            f"Успешность доставки: <b>{summary.success_rate_pct:.1f}%</b>",
            f"Доля ошибок: <b>{summary.error_rate_pct:.1f}%</b>",
            f"Среднее время подготовки: <b>{summary.avg_generation_ms} мс</b>",
            f"Среднее время доставки: <b>{summary.avg_delivery_ms} мс</b>",
        ]
    )


def _full_name(row: dict) -> str:
    return " ".join(
        part for part in [row.get("last_name"), row.get("first_name"), row.get("middle_name")] if part
    ) or "—"


def _build_pdf_lines(period: str, summary, rows: list[dict]) -> list[str]:
    lines = [
        f"TimeWise - Отчет по рассылкам ({_period_label(period)})",
        "",
        "Сводка:",
        f"Всего событий: {summary.total_events}",
        f"Одобрено: {summary.approved_messages}",
        f"На согласовании: {summary.pending_approvals}",
        f"Отклонено: {summary.rejected_approvals}",
        f"Отправлено: {summary.sent_messages}",
        f"Ошибок: {summary.failed_jobs}",
        f"С ретраями: {summary.retried_jobs}",
        f"Успешность доставки: {summary.success_rate_pct:.1f}%",
        f"Доля ошибок: {summary.error_rate_pct:.1f}%",
        f"Среднее время подготовки: {summary.avg_generation_ms} мс",
        f"Среднее время доставки: {summary.avg_delivery_ms} мс",
        "",
        "Реестр:",
    ]
    if not rows:
        lines.append("Нет данных за выбранный период.")
        return lines

    for row in rows:
        lines.extend(
            [
                (
                    f"event_id={row.get('event_id')} | дата={row.get('event_date')} | "
                    f"контакт={_full_name(row)} | канал={row.get('channel') or '—'} | "
                    f"стиль={row.get('style') or '—'}"
                ),
                (
                    f"статус события={row.get('event_status') or '—'} | "
                    f"согласование={row.get('approval_status') or '—'} | "
                    f"job={row.get('job_status') or '—'} | retry={row.get('retry_count') or 0}"
                ),
                (
                    f"компания={row.get('company') or '—'} | должность={row.get('position') or '—'} | "
                    f"approved_at={row.get('approved_at') or '—'} | sent_at={row.get('sent_at') or '—'}"
                ),
                f"last_error={row.get('last_error') or '—'}",
                "",
            ]
        )
    return lines


def _build_registry_pdf(period: str, summary, rows: list[dict]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = _register_pdf_font()
    line_height = 14
    margin_x = 40
    y = height - 40

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        pdf.setFont(font_name, 10)
        y = height - 40

    pdf.setTitle(f"TimeWise report {period}")
    pdf.setFont(font_name, 10)

    for raw_line in _build_pdf_lines(period, summary, rows):
        wrapped = textwrap.wrap(str(raw_line), width=95, break_long_words=False) or [""]
        for line in wrapped:
            if y <= 40:
                new_page()
            pdf.drawString(margin_x, y, line)
            y -= line_height

    pdf.save()
    return buffer.getvalue()


def _build_registry_csv(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "event_id",
            "event_date",
            "contact_id",
            "full_name",
            "company",
            "position",
            "channel",
            "style",
            "event_status",
            "approval_status",
            "job_status",
            "retry_count",
            "message_id",
            "approved_at",
            "sent_at",
            "last_error",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("event_id"),
                row.get("event_date"),
                row.get("contact_id"),
                _full_name(row),
                row.get("company") or "",
                row.get("position") or "",
                row.get("channel") or "",
                row.get("style") or "",
                row.get("event_status") or "",
                row.get("approval_status") or "",
                row.get("job_status") or "",
                row.get("retry_count") or 0,
                row.get("message_id") or "",
                row.get("approved_at") or "",
                row.get("sent_at") or "",
                row.get("last_error") or "",
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


async def _render_reports(callback: CallbackQuery, *, period: str, role: UserRole | None) -> None:
    if callback.message is None:
        return
    async with _sessionmaker() as session:
        summary = await get_report_summary(session, period=period)
    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _build_report_text(period, summary),
        reply_markup=reports_menu(period=period, back_cb=_reports_back_cb(role)),
    )


@router.callback_query(F.data.in_({"reports:root", "reports:today", "reports:month", "reports:all"}))
async def reports_root(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_access_reports(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    period = "month"
    if callback.data and callback.data.startswith("reports:") and callback.data != "reports:root":
        period = callback.data.split(":")[-1]
    await _render_reports(callback, period=period, role=role)


@router.callback_query(F.data.startswith("reports:csv:"))
async def reports_csv(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_access_reports(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    period = callback.data.split(":")[-1]
    try:
        async with _sessionmaker() as session:
            rows = await get_report_registry(session, period=period, limit=1000)
        filename = f"timewise_report_{period}.csv"
        document = BufferedInputFile(_build_registry_csv(rows), filename=filename)
        await callback.message.answer_document(
            document,
            caption=f"Реестр рассылок за период: <b>{_period_label(period)}</b>",
        )
    except Exception as e:
        logger.exception("CSV report failed (%s): %s", period, e)
        await callback.message.answer("😔 Не удалось сформировать CSV-отчет.")


@router.callback_query(F.data.startswith("reports:pdf:"))
async def reports_pdf(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_access_reports(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    period = callback.data.split(":")[-1]
    try:
        async with _sessionmaker() as session:
            summary = await get_report_summary(session, period=period)
            rows = await get_report_registry(session, period=period, limit=1000)
        filename = f"timewise_report_{period}.pdf"
        document = BufferedInputFile(_build_registry_pdf(period, summary, rows), filename=filename)
        await callback.message.answer_document(
            document,
            caption=f"PDF-отчет за период: <b>{_period_label(period)}</b>",
        )
    except Exception as e:
        logger.exception("PDF report failed (%s): %s", period, e)
        await callback.message.answer("😔 Не удалось сформировать PDF-отчет.")


@router.message(Command("stats"))
async def stats_command(message: Message, role: UserRole | None = None) -> None:
    if role != UserRole.ADMIN:
        await message.answer("⛔ Команда /stats доступна только Admin.")
        return
    try:
        async with _sessionmaker() as session:
            summary = await get_report_summary(session, period="today")
        await message.answer(_build_stats_text(summary))
    except Exception as e:
        logger.exception("Stats command failed: %s", e)
        await message.answer("😔 Не удалось загрузить статистику.")


@router.callback_query(F.data.startswith("viewer:"))
async def viewer_action_handler(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_viewer(role):
        await callback.answer("⛔ Доступ только для роли Viewer.", show_alert=True)
        return
    if callback.message is None:
        logger.warning("callback.message is None for user %s", callback.from_user.id)
        return

    data = callback.data or ""
    try:
        if data == "viewer:stats":
            async with _sessionmaker() as session:
                tables = await get_table_counts(
                    session, ["contacts", "events", "messages", "job_queue", "approval_queue", "templates"]
                )
                event_status = await get_status_counts(session, table="events")
            lines = ["📈 <b>Статистика</b>", ""]
            lines.append("<b>Объёмы</b>")
            for t in tables:
                lines.append(f"- <b>{t.table}</b>: {t.total}")
            lines.append("")
            lines.append("<b>events.status</b>")
            if event_status:
                for s in event_status[:8]:
                    lines.append(f"- <code>{s.get('status')}</code>: {s.get('c')}")
            else:
                lines.append("- —")
            text = "\n".join(lines)
        elif data == "viewer:events":
            async with _sessionmaker() as session:
                rows = await list_events(session, limit=12)
            lines = ["📅 <b>События (последние)</b>", ""]
            if not rows:
                lines.append("Пусто.")
            else:
                for r in rows:
                    who = "—"
                    if r.get("last_name") or r.get("first_name"):
                        who = f"{r.get('last_name') or ''} {r.get('first_name') or ''}".strip()
                    lines.append(
                        f"- <code>{r.get('id')}</code> {r.get('date')} <code>{r.get('status')}</code> "
                        f"{r.get('channel')}/{r.get('style')} — {who}"
                    )
            text = "\n".join(lines)
        elif data == "viewer:messages":
            async with _sessionmaker() as session:
                rows = await list_messages(session, limit=12)
            lines = ["✉️ <b>Сообщения (последние)</b>", ""]
            if not rows:
                lines.append("Пусто.")
            else:
                for r in rows:
                    sent = "✅" if r.get("sent_at") else "—"
                    appr = "✅" if r.get("approved_at") else "—"
                    lines.append(
                        f"- <code>{r.get('id')}</code> ev=<code>{r.get('event_id')}</code> "
                        f"tpl=<code>{r.get('template_id')}</code> "
                        f"одобрено:{appr} доставлено:{sent}"
                    )
            text = "\n".join(lines)
        else:
            text = VIEWER_HINTS.get(data, "🚧 Раздел в разработке.")
    except Exception as e:
        logger.exception("Viewer section failed (%s): %s", data, e)
        text = "😔 Не удалось загрузить данные из БД. Проверьте логи и права доступа."

    try:
        await clear_temp_messages(callback.message)
        await safe_edit_text(callback.message, text, reply_markup=user_back_panel())
    except Exception as e:
        logger.debug("Не удалось отредактировать сообщение: %s", e)
        await callback.message.answer(text, reply_markup=user_back_panel())

