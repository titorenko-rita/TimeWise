"""ApprovalQueue: просмотр и согласование заявок."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db.repositories.approvals import (
    approve,
    bulk_approve_today,
    bulk_reject_today,
    count_today_pending_approval_breakdown,
    edit_rendered_text,
    get_approval_card,
    list_approvals,
    list_today_pending_approval_ids,
    reject,
)
from db.session import get_sessionmaker
from keyboards.approvals import approval_detail_menu, approvals_list_menu
from keyboards.panels import panel_by_role
from roles import UserRole
from ui_helpers import clear_temp_messages, safe_edit_text, send_temp_message

logger = logging.getLogger(__name__)
router = Router(name="approvals_handlers")
_sessionmaker = get_sessionmaker()

PAGE_SIZE = 6


class EditApprovalState(StatesGroup):
    waiting_for_text = State()


def _can_access(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


def _is_admin(role: UserRole | None) -> bool:
    return role == UserRole.ADMIN


def _parse_event_kind(raw: str | None) -> str:
    return raw if raw in {"all", "birthday", "holiday"} else "all"


def _event_kind_label(event_kind: str) -> str:
    return {
        "all": "все заявки",
        "birthday": "только дни рождения",
        "holiday": "только другие праздники",
    }.get(event_kind, "все заявки")


def _approval_status_ru(status: str) -> str:
    return {
        "pending": "на согласовании",
        "edited": "правки внесены",
        "approved": "одобрено",
        "rejected": "отклонено",
    }.get(status, status)


def _ru_channel(channel: str | None) -> str:
    return {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}.get(channel or "—", channel or "—")


def _ru_style(style: str | None) -> str:
    return {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}.get(
        style or "—", style or "—"
    )


def _menu_text_for_role(role: UserRole | None) -> str:
    if role == UserRole.ADMIN:
        title = "🔧 <b>Панель администратора</b>"
    elif role == UserRole.EDITOR:
        title = "✍️ <b>Панель редактора</b>"
    else:
        title = "👁 <b>Панель просмотра</b>"
    return f"{title}\n\nВыберите раздел:"


def _parse_callback_with_kind(data: str | None, id_index: int) -> tuple[int | None, str]:
    if not data:
        return None, "all"
    parts = data.split(":")
    try:
        value = int(parts[id_index])
    except (IndexError, ValueError):
        return None, "all"
    event_kind = _parse_event_kind(parts[id_index + 1] if len(parts) > id_index + 1 else "all")
    return value, event_kind


def _fmt_card(card) -> str:
    who = card.contact_name or "—"
    date = str(card.event_date) if card.event_date else "—"
    resp = f"<code>{card.responsible_tg_id}</code>" if card.responsible_tg_id else "—"
    parts = [
        "✅ <b>Согласование</b>",
        "",
        f"id: <code>{card.approval_id}</code>",
        f"статус: <b>{html.escape(_approval_status_ru(card.approval_status))}</b> <code>({html.escape(card.approval_status)})</code>",
        f"event_id: <code>{card.event_id}</code>",
        f"дата: <b>{html.escape(date)}</b>",
        f"канал/стиль: <b>{html.escape(_ru_channel(card.channel))}</b> / <b>{html.escape(_ru_style(card.style))}</b>",
        f"кому: <b>{html.escape(who)}</b>",
        f"tg_username: <code>{html.escape(card.contact_tg_username or '—')}</code>",
        f"email: <code>{html.escape(card.contact_email or '—')}</code>",
        f"должность: <b>{html.escape(card.contact_position or '—')}</b>",
        f"компания: <b>{html.escape(card.contact_company or '—')}</b>",
        f"заметки: {html.escape((card.contact_notes or '—')[:250])}",
        f"ответственный (tg_id): {resp}",
    ]
    if card.approval_comment:
        parts += ["", f"комментарий: {html.escape(str(card.approval_comment))}"]
    if card.message_id:
        parts += ["", f"message_id: <code>{card.message_id}</code>"]
        if card.approved_at:
            parts.append(f"одобрено: <code>{card.approved_at}</code>")
        if card.sent_at:
            parts.append(f"отправлено: <code>{card.sent_at}</code>")
    return "\n".join(parts)


async def _send_rendered_text(message: Message, text: str | None) -> None:
    rendered = (text or "").strip()
    if not rendered:
        await send_temp_message(message, "<i>(текст пуст)</i>")
        return
    escaped = html.escape(rendered)
    chunk_size = 3500
    chunks = [escaped[i : i + chunk_size] for i in range(0, len(escaped), chunk_size)]
    for idx, chunk in enumerate(chunks[:6]):
        prefix = "" if idx == 0 else f"<b>Продолжение {idx + 1}</b>\n"
        await send_temp_message(message, prefix + f"<pre>{chunk}</pre>")
    if len(chunks) > 6:
        await send_temp_message(message, "…текст слишком длинный, показана только часть.")


async def _build_batch_detail(
    *,
    approval_id: int,
    role: UserRole | None,
    actor_user_id: int | None,
    event_kind: str,
) -> tuple[str, object, str | None] | None:
    async with _sessionmaker() as session:
        batch_ids = await list_today_pending_approval_ids(
            session,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
            event_kind=event_kind,
        )
        if not batch_ids:
            return None
        if approval_id not in batch_ids:
            approval_id = batch_ids[0]

        card = await get_approval_card(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
        )

    if card is None:
        return None

    idx = batch_ids.index(approval_id)
    prev_id = batch_ids[idx - 1] if idx > 0 else None
    next_id = batch_ids[idx + 1] if idx + 1 < len(batch_ids) else None
    text = (
        "✏️ <b>Правка сегодняшней пачки</b>\n\n"
        f"Заявка <b>{idx + 1}</b> из <b>{len(batch_ids)}</b>\n"
        f"Фильтр: <b>{html.escape(_event_kind_label(event_kind))}</b>\n\n"
        f"{_fmt_card(card)}"
    )
    markup = approval_detail_menu(
        approval_id=approval_id,
        can_act=_can_access(role),
        event_kind=event_kind,
        batch_mode=True,
        prev_approval_id=prev_id,
        next_approval_id=next_id,
    )
    return text, markup, card.rendered_text


async def _open_batch_approval(
    callback: CallbackQuery,
    *,
    approval_id: int,
    role: UserRole | None,
    actor_user_id: int | None,
    event_kind: str,
) -> bool:
    if callback.message is None:
        return False

    detail = await _build_batch_detail(
        approval_id=approval_id,
        role=role,
        actor_user_id=actor_user_id,
        event_kind=event_kind,
    )
    if detail is None:
        await send_temp_message(callback.message, "Сегодня в пачке нет заявок для правки.")
        await _approvals_list(
            callback,
            page=0,
            event_kind=event_kind,
            role=role,
            actor_user_id=actor_user_id,
        )
        return False

    text, markup, rendered_text = detail
    await clear_temp_messages(callback.message)
    await safe_edit_text(callback.message, text, reply_markup=markup)
    await send_temp_message(callback.message, "<b>Текст сообщения</b>:")
    await _send_rendered_text(callback.message, rendered_text)
    return True


@router.callback_query(F.data.in_({"admin:approvals", "approvals:list"}))
async def approvals_root(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    await _approvals_list(callback, page=0, event_kind="all", role=role, actor_user_id=actor_user_id)


@router.callback_query(F.data.startswith("approvals:list:"))
async def approvals_list_page(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.data is None:
        return
    parts = callback.data.split(":")
    try:
        page = int(parts[2])
    except (IndexError, ValueError):
        page = 0
    event_kind = _parse_event_kind(parts[3] if len(parts) > 3 else "all")
    await _approvals_list(
        callback,
        page=max(page, 0),
        event_kind=event_kind,
        role=role,
        actor_user_id=actor_user_id,
    )


async def _approvals_list(
    callback: CallbackQuery,
    *,
    page: int,
    event_kind: str,
    role: UserRole | None,
    actor_user_id: int | None,
) -> None:
    if callback.message is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    try:
        async with _sessionmaker() as session:
            items = await list_approvals(
                session,
                actor_user_id=actor_user_id,
                is_admin=_is_admin(role),
                event_kind=event_kind,
                limit=PAGE_SIZE + 1,
                offset=page * PAGE_SIZE,
            )
            today_birthdays, today_holidays = await count_today_pending_approval_breakdown(
                session,
                actor_user_id=actor_user_id,
                is_admin=_is_admin(role),
            )
        has_next = len(items) > PAGE_SIZE
        items = items[:PAGE_SIZE]
        title = "✅ <b>Очередь согласования</b>"
        note = "Вы видите только свои заявки." if role == UserRole.EDITOR else "Вы видите все заявки."
        batch_note = (
            "Сегодня ждут решения "
            f"(дни рождения: <b>{today_birthdays}</b> и другие праздники: <b>{today_holidays}</b>)."
        )
        filter_note = f"Фильтр: <b>{html.escape(_event_kind_label(event_kind))}</b>."
        text = (
            f"{title}\n\n{note}\n{batch_note}\n{filter_note}\n\n"
            "Сначала «на согласовании», затем остальные статусы."
        )
        kb = approvals_list_menu(
            items=items,
            page=page,
            has_next=has_next,
            can_batch=_is_admin(role),
            event_kind=event_kind,
            back_cb="nav:admin_menu" if role == UserRole.ADMIN else "nav:user_menu",
        )
        await clear_temp_messages(callback.message)
        await safe_edit_text(callback.message, text, reply_markup=kb)
    except Exception as exc:
        logger.exception("approvals list failed: %s", exc)
        await callback.message.answer("😔 Не удалось загрузить заявки из БД.")


@router.callback_query(F.data.startswith("approvals:open:"))
async def approval_open(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    async with _sessionmaker() as session:
        card = await get_approval_card(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
        )
    if card is None:
        await callback.message.answer("Заявка не найдена.")
        return

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _fmt_card(card),
        reply_markup=approval_detail_menu(
            approval_id=approval_id,
            can_act=_can_access(role),
            event_kind=event_kind,
        ),
    )
    await send_temp_message(callback.message, "<b>Текст сообщения</b>:")
    await _send_rendered_text(callback.message, card.rendered_text)


@router.callback_query(F.data.startswith("approvals:batch_edit_today"))
async def approvals_batch_edit_today(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if role != UserRole.ADMIN:
        await callback.answer("⛔ Доступ только для Admin.", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    event_kind = _parse_event_kind(parts[3] if len(parts) > 3 else "all")
    async with _sessionmaker() as session:
        batch_ids = await list_today_pending_approval_ids(
            session,
            actor_user_id=actor_user_id,
            is_admin=True,
            event_kind=event_kind,
        )
    if not batch_ids:
        await send_temp_message(callback.message, "Сегодня нет заявок для правки по выбранному фильтру.")
        return
    await _open_batch_approval(
        callback,
        approval_id=batch_ids[0],
        role=role,
        actor_user_id=actor_user_id,
        event_kind=event_kind,
    )


@router.callback_query(F.data.startswith("approvals:batch_open:"))
async def approval_batch_open(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return
    await _open_batch_approval(
        callback,
        approval_id=approval_id,
        role=role,
        actor_user_id=actor_user_id,
        event_kind=event_kind,
    )


@router.callback_query(F.data.startswith("approvals:approve:"))
async def approval_approve(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    async with _sessionmaker() as session:
        if actor_user_id is None:
            await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
            return
        ok, msg = await approve(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
        )
    if ok:
        await callback.answer(msg)
        await _approvals_list(
            callback,
            page=0,
            event_kind=event_kind,
            role=role,
            actor_user_id=actor_user_id,
        )
        return
    await send_temp_message(callback.message, msg, reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("approvals:batch_approve:"))
async def approval_batch_approve(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    async with _sessionmaker() as session:
        if actor_user_id is None:
            await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
            return
        ok, msg = await approve(session, approval_id=approval_id, actor_user_id=actor_user_id, is_admin=True)
    if ok:
        await callback.answer(msg)
        await _open_batch_approval(
            callback,
            approval_id=approval_id,
            role=role,
            actor_user_id=actor_user_id,
            event_kind=event_kind,
        )
        return
    await send_temp_message(callback.message, msg, reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("approvals:batch_approve_today"))
async def approvals_batch_approve_today(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer("Запускаю пакетное одобрение...", show_alert=False)
    if callback.message is None:
        return
    if role != UserRole.ADMIN:
        await callback.answer("⛔ Доступ только для Admin.", show_alert=True)
        return
    if actor_user_id is None:
        await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
        return

    parts = (callback.data or "").split(":")
    event_kind = _parse_event_kind(parts[3] if len(parts) > 3 else "all")
    await callback.message.answer("⏳ Начинаю пакетное одобрение заявок за сегодня. Это может занять несколько секунд.")

    async with _sessionmaker() as session:
        approved, skipped, errors = await bulk_approve_today(
            session,
            actor_user_id=actor_user_id,
            is_admin=True,
            event_kind=event_kind,
        )

    lines = [
        "✅ <b>Пакетное согласование завершено</b>",
        "",
        f"Одобрено сегодня: <b>{approved}</b>",
        f"Пропущено: <b>{skipped}</b>",
        f"Фильтр: <b>{html.escape(_event_kind_label(event_kind))}</b>",
    ]
    if errors:
        lines.extend(["", "<b>Проблемы</b>"])
        lines.extend(f"- {error}" for error in errors)

    await callback.message.answer("\n".join(lines))
    await callback.message.answer(_menu_text_for_role(role), reply_markup=panel_by_role(role))


@router.callback_query(F.data.startswith("approvals:batch_reject_today"))
async def approvals_batch_reject_today(
    callback: CallbackQuery,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if role != UserRole.ADMIN:
        await callback.answer("⛔ Доступ только для Admin.", show_alert=True)
        return
    if actor_user_id is None:
        await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
        return

    parts = (callback.data or "").split(":")
    event_kind = _parse_event_kind(parts[3] if len(parts) > 3 else "all")
    async with _sessionmaker() as session:
        rejected, skipped, errors = await bulk_reject_today(
            session,
            actor_user_id=actor_user_id,
            is_admin=True,
            event_kind=event_kind,
        )

    lines = [
        "⛔ <b>Пакетная отмена завершена</b>",
        "",
        f"Отклонено сегодня: <b>{rejected}</b>",
        f"Пропущено: <b>{skipped}</b>",
    ]
    if errors:
        lines.extend(["", "<b>Проблемы</b>"])
        lines.extend(f"- {error}" for error in errors)
    await callback.answer(f"Отклонено: {rejected}", show_alert=False)
    await send_temp_message(callback.message, "\n".join(lines))
    await _approvals_list(
        callback,
        page=0,
        event_kind=event_kind,
        role=role,
        actor_user_id=actor_user_id,
    )


@router.callback_query(F.data.startswith("approvals:reject:"))
async def approval_reject(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    async with _sessionmaker() as session:
        if actor_user_id is None:
            await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
            return
        ok, msg = await reject(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
        )
    if ok:
        await callback.answer(msg)
        await _approvals_list(
            callback,
            page=0,
            event_kind=event_kind,
            role=role,
            actor_user_id=actor_user_id,
        )
        return
    await send_temp_message(callback.message, msg, reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("approvals:batch_reject:"))
async def approval_batch_reject(
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

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    async with _sessionmaker() as session:
        if actor_user_id is None:
            await callback.message.answer("⛔ Ваш пользователь не найден в таблице users.")
            return
        ok, msg = await reject(session, approval_id=approval_id, actor_user_id=actor_user_id, is_admin=True)
    if ok:
        await callback.answer(msg)
        await _open_batch_approval(
            callback,
            approval_id=approval_id,
            role=role,
            actor_user_id=actor_user_id,
            event_kind=event_kind,
        )
        return
    await send_temp_message(callback.message, msg, reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data.startswith("approvals:edit:"))
async def approval_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
    role: UserRole | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if not _can_access(role):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    await state.set_state(EditApprovalState.waiting_for_text)
    await state.update_data(approval_id=approval_id, event_kind=event_kind)
    await callback.message.answer(
        "✏️ Отправьте новый <b>rendered_text</b> одним сообщением.\n\n"
        "Чтобы отменить — отправьте /cancel."
    )


@router.callback_query(F.data.startswith("approvals:batch_edit:"))
async def approval_batch_edit_start(
    callback: CallbackQuery,
    state: FSMContext,
    role: UserRole | None = None,
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    if role != UserRole.ADMIN:
        await callback.answer("⛔ Доступ только для Admin.", show_alert=True)
        return

    approval_id, event_kind = _parse_callback_with_kind(callback.data, 2)
    if approval_id is None:
        return

    await state.set_state(EditApprovalState.waiting_for_text)
    await state.update_data(approval_id=approval_id, batch_mode=True, event_kind=event_kind)
    await callback.message.answer(
        "✏️ Отправьте новый <b>rendered_text</b> для текущей заявки из пачки.\n\n"
        "Чтобы отменить — отправьте /cancel."
    )


@router.message(EditApprovalState.waiting_for_text)
async def approval_edit_receive(
    message: Message,
    state: FSMContext,
    role: UserRole | None = None,
    actor_user_id: int | None = None,
) -> None:
    if not _can_access(role):
        await state.clear()
        await message.answer("⛔ Доступ запрещён.")
        return
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    data = await state.get_data()
    approval_id = data.get("approval_id")
    batch_mode = bool(data.get("batch_mode"))
    event_kind = _parse_event_kind(data.get("event_kind"))
    if not isinstance(approval_id, int):
        await state.clear()
        await message.answer("Сценарий сброшен. Откройте заявку заново.")
        return

    new_text = message.text or ""
    await state.clear()
    async with _sessionmaker() as session:
        if actor_user_id is None:
            await message.answer("⛔ Ваш пользователь не найден в таблице users.")
            return
        ok, msg = await edit_rendered_text(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=_is_admin(role),
            new_text=new_text,
        )
    if ok:
        if batch_mode:
            await message.answer(msg)
            detail = await _build_batch_detail(
                approval_id=approval_id,
                role=role,
                actor_user_id=actor_user_id,
                event_kind=event_kind,
            )
            if detail is None:
                await message.answer("Сегодняшняя пачка уже обработана.", reply_markup=panel_by_role(role or UserRole.VIEWER))
                return
            text, markup, rendered_text = detail
            await message.answer(text, reply_markup=markup)
            await send_temp_message(message, "Обновлённый текст:")
            await _send_rendered_text(message, rendered_text)
            return
        await message.answer(msg, reply_markup=panel_by_role(role or UserRole.VIEWER))
        await send_temp_message(message, "Обновлённый текст:")
        await _send_rendered_text(message, new_text)
        return
    await message.answer(msg, reply_markup=panel_by_role(role or UserRole.VIEWER))
