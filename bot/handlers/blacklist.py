"""Управление черным списком слов и фраз."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db.repositories.blacklist import (
    count_blacklist_entries,
    create_blacklist_entry,
    delete_blacklist_entry,
    get_blacklist_entry,
    list_blacklist_entries,
)
from db.session import get_sessionmaker
from keyboards.blacklist import (
    blacklist_delete_confirm_menu,
    blacklist_detail_menu,
    blacklist_list_menu,
)
from roles import UserRole
from ui_helpers import clear_temp_messages, safe_edit_text, send_temp_message

logger = logging.getLogger(__name__)
router = Router(name="blacklist_handlers")
_sessionmaker = get_sessionmaker()

PAGE_SIZE = 8


class AddBlacklistState(StatesGroup):
    waiting_for_phrase = State()


def _can_manage(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


def _format_list_text(*, page: int, total: int) -> str:
    return (
        "🚫 <b>Чёрный список</b>\n\n"
        f"Запрещённые слова и фразы: <b>{total}</b>.\n"
        f"Страница <b>{page + 1}</b>.\n\n"
        "Нажмите на запись, чтобы открыть и удалить её."
    )


def _format_detail_text(entry_id: int, phrase: str) -> str:
    return (
        "🚫 <b>Запись чёрного списка</b>\n\n"
        f"id: <code>{entry_id}</code>\n"
        f"фраза: <code>{html.escape(phrase)}</code>"
    )


async def _render_blacklist_list(callback: CallbackQuery, *, page: int, role: UserRole | None) -> None:
    if callback.message is None:
        return

    offset = page * PAGE_SIZE
    async with _sessionmaker() as session:
        total = await count_blacklist_entries(session)
        items = await list_blacklist_entries(session, limit=PAGE_SIZE, offset=offset)

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _format_list_text(page=page, total=total),
        reply_markup=blacklist_list_menu(
            items=items,
            page=page,
            page_size=PAGE_SIZE,
            total=total,
            can_manage=_can_manage(role),
        ),
    )


async def _edit_source_list(
    message: Message,
    *,
    source_chat_id: int,
    source_message_id: int,
    role: UserRole | None,
) -> None:
    async with _sessionmaker() as session:
        total = await count_blacklist_entries(session)
        items = await list_blacklist_entries(session, limit=PAGE_SIZE, offset=0)

    await clear_temp_messages(message)
    await message.bot.edit_message_text(
        chat_id=source_chat_id,
        message_id=source_message_id,
        text=_format_list_text(page=0, total=total),
        reply_markup=blacklist_list_menu(
            items=items,
            page=0,
            page_size=PAGE_SIZE,
            total=total,
            can_manage=_can_manage(role),
        ),
    )


async def _send_blacklist_list_message(message: Message, *, role: UserRole | None) -> None:
    async with _sessionmaker() as session:
        total = await count_blacklist_entries(session)
        items = await list_blacklist_entries(session, limit=PAGE_SIZE, offset=0)

    await message.answer(
        _format_list_text(page=0, total=total),
        reply_markup=blacklist_list_menu(
            items=items,
            page=0,
            page_size=PAGE_SIZE,
            total=total,
            can_manage=_can_manage(role),
        ),
    )


@router.callback_query(F.data.in_({"admin:blacklist", "blacklist:list"}))
async def blacklist_root(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    await _render_blacklist_list(callback, page=0, role=role)


@router.callback_query(F.data.startswith("blacklist:list:"))
async def blacklist_list_page(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.data is None:
        return
    try:
        page = int(callback.data.split(":")[-1])
    except ValueError:
        page = 0
    await _render_blacklist_list(callback, page=max(page, 0), role=role)


@router.callback_query(F.data == "blacklist:add")
async def blacklist_add_prompt(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return

    await state.set_state(AddBlacklistState.waiting_for_phrase)
    await state.update_data(
        source_chat_id=callback.message.chat.id,
        source_message_id=callback.message.message_id,
    )
    await send_temp_message(
        callback.message,
        "✏️ Отправьте слово или словосочетание, которое нужно добавить в <b>чёрный список</b>.\n\n"
        "Чтобы отменить, отправьте <code>/cancel</code>.",
    )


@router.message(AddBlacklistState.waiting_for_phrase)
async def blacklist_add_receive(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage(role):
        await state.clear()
        await message.answer("⛔ Доступ запрещён.")
        return

    raw = (message.text or "").strip()
    if raw == "/cancel":
        await state.clear()
        await send_temp_message(message, "Добавление в чёрный список отменено.")
        return
    if not raw:
        await message.answer("Введите непустое слово или словосочетание.")
        return

    data = await state.get_data()
    await state.clear()

    async with _sessionmaker() as session:
        entry, created = await create_blacklist_entry(
            session,
            phrase=raw,
            actor_tg_id=message.from_user.id if message.from_user else None,
        )

    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if isinstance(source_chat_id, int) and isinstance(source_message_id, int):
        await _edit_source_list(
            message,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            role=role,
        )

    if entry is None:
        await send_temp_message(message, "Не удалось добавить фразу: пустое значение.")
        return
    if created:
        await send_temp_message(
            message,
            f"✅ Фраза добавлена в чёрный список: <code>{html.escape(entry.phrase)}</code>.",
        )
        await _send_blacklist_list_message(message, role=role)
        return

    await send_temp_message(
        message,
        f"ℹ️ Такая фраза уже есть в чёрном списке: <code>{html.escape(entry.phrase)}</code>.",
    )
    await _send_blacklist_list_message(message, role=role)


@router.callback_query(F.data.startswith("blacklist:open:"))
async def blacklist_open(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        entry_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        entry = await get_blacklist_entry(session, entry_id)
    if entry is None:
        await callback.message.answer("Запись чёрного списка не найдена.")
        return

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _format_detail_text(entry.id, entry.phrase),
        reply_markup=blacklist_detail_menu(entry_id=entry.id, can_manage=_can_manage(role)),
    )


@router.callback_query(F.data.startswith("blacklist:delete:"))
async def blacklist_delete_prompt(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        entry_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        entry = await get_blacklist_entry(session, entry_id)
    if entry is None:
        await callback.message.answer("Запись чёрного списка не найдена.")
        return

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        "🗑 <b>Удалить запись из чёрного списка?</b>\n\n"
        f"id: <code>{entry.id}</code>\n"
        f"фраза: <code>{html.escape(entry.phrase)}</code>\n\n"
        "Удаление будет выполнено <b>полностью</b>.",
        reply_markup=blacklist_delete_confirm_menu(entry.id),
    )


@router.callback_query(F.data.startswith("blacklist:delete_confirm:"))
async def blacklist_delete_confirm(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        entry_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        ok = await delete_blacklist_entry(
            session,
            entry_id=entry_id,
            actor_tg_id=callback.from_user.id if callback.from_user else None,
        )
    if not ok:
        await callback.message.answer("Запись чёрного списка не найдена или уже удалена.")
        return

    await _render_blacklist_list(callback, page=0, role=role)
    await send_temp_message(callback.message, "✅ Запись удалена из чёрного списка.")
