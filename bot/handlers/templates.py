"""Управление шаблонами (templates) через Telegram."""

from __future__ import annotations

import html
import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.templates import (
    count_templates,
    create_new_version,
    get_template_by_id,
    list_latest_templates,
    list_versions,
    soft_delete,
    toggle_active,
    update_body_text,
)
from db.session import get_sessionmaker
from keyboards.templates import (
    template_delete_confirm_menu,
    template_detail_menu,
    template_versions_menu,
    templates_list_menu,
)
from roles import UserRole
from ui_helpers import clear_temp_messages, safe_edit_text, send_temp_message

logger = logging.getLogger(__name__)
router = Router(name="templates_handlers")
_sessionmaker = get_sessionmaker()

PAGE_SIZE = 8


class EditTemplateState(StatesGroup):
    waiting_for_body = State()


class SearchTemplateState(StatesGroup):
    waiting_for_id = State()


def _can_edit(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


def _safe_preview(text: str, ctx: dict[str, str]) -> str:
    s = text.replace("{{", "{").replace("}}", "}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return ctx.get(key, match.group(0))

    return re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", repl, s)


def _ru_channel(ch: str) -> str:
    return {"Telegram": "Телеграм", "Email": "Email", "SMS": "SMS"}.get(ch, ch)


def _ru_style(st: str) -> str:
    return {"Business": "Деловой", "Official": "Официальный", "Friendly": "Дружеский"}.get(st, st)


def _ru_case(case_name: str) -> str:
    return {
        "Nominative": "Именительный",
        "Genitive": "Родительный",
        "Dative": "Дательный",
        "Accusative": "Винительный",
        "Instrumental": "Творительный",
        "Prepositional": "Предложный",
    }.get(case_name, case_name)


def _ru_language(lang: str) -> str:
    return {"ru": "Русский", "en": "Английский"}.get(lang, lang)


def _fmt_template_card(template) -> str:
    status = "✅ активен" if template.is_active else "⛔ выключен"
    return (
        "📝 <b>Шаблон</b>\n\n"
        f"id: <code>{template.id}</code>\n"
        f"категория: <b>{html.escape(template.category)}</b>\n"
        f"канал: <b>{html.escape(_ru_channel(template.channel))}</b> <code>({html.escape(template.channel)})</code>\n"
        f"стиль: <b>{html.escape(_ru_style(template.style))}</b> <code>({html.escape(template.style)})</code>\n"
        f"падеж: <b>{html.escape(_ru_case(template.case))}</b> <code>({html.escape(template.case)})</code>\n"
        f"язык: <b>{html.escape(_ru_language(template.language))}</b> <code>({html.escape(template.language)})</code>\n"
        f"версия: <b>{template.version}</b>\n"
        f"статус: <b>{status}</b>\n"
    )


async def _send_body_text(message: Message, body_text: str) -> None:
    text = body_text or ""
    if not text.strip():
        await send_temp_message(message, "<i>(пустой текст)</i>")
        return

    escaped = html.escape(text)
    chunk_size = 3500
    chunks = [escaped[i : i + chunk_size] for i in range(0, len(escaped), chunk_size)]
    for idx, chunk in enumerate(chunks[:6]):
        prefix = "" if idx == 0 else f"<b>Продолжение {idx + 1}</b>\n"
        await send_temp_message(message, prefix + f"<pre>{chunk}</pre>")
    if len(chunks) > 6:
        await send_temp_message(message, "…текст слишком длинный, показана только часть.")


async def _show_template_message(
    message: Message,
    *,
    template_id: int,
    role: UserRole | None,
) -> None:
    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)
    if template is None or template.is_deleted:
        await message.answer("Шаблон не найден.")
        return

    can_edit = _can_edit(role)
    await message.answer(
        _fmt_template_card(template),
        reply_markup=template_detail_menu(
            template_id=template.id,
            is_active=template.is_active,
            can_edit=can_edit,
        ),
    )
    await send_temp_message(message, "<b>Текст шаблона</b>:", disable_web_page_preview=True)
    await _send_body_text(message, template.body_text)


async def _templates_list_page(callback: CallbackQuery, *, page: int, role: UserRole | None) -> None:
    if callback.message is None:
        return

    offset = page * PAGE_SIZE
    try:
        await clear_temp_messages(callback.message)
        async with _sessionmaker() as session:
            total = await count_templates(session)
            items = await list_latest_templates(session, limit=PAGE_SIZE, offset=offset)
        title = "📝 <b>Шаблоны</b>"
        text = f"{title}\n\nПоказаны шаблоны по возрастанию id (страница {page + 1})."
        keyboard = templates_list_menu(items=items, page=page, page_size=PAGE_SIZE, total=total)
        await safe_edit_text(callback.message, text, reply_markup=keyboard)
    except Exception as exc:
        logger.exception("templates list failed: %s", exc)
        await callback.message.answer("😔 Не удалось загрузить шаблоны из БД.")


@router.callback_query(F.data.in_({"templates:list", "admin:templates"}))
async def templates_list_root(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    await _templates_list_page(callback, page=0, role=role)


@router.callback_query(F.data.startswith("templates:list:"))
async def templates_list_page(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.data is None:
        return
    try:
        page = int(callback.data.split(":")[-1])
    except ValueError:
        page = 0
    await _templates_list_page(callback, page=max(page, 0), role=role)


@router.callback_query(F.data == "templates:search")
async def templates_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SearchTemplateState.waiting_for_id)
    if callback.message is None:
        return
    await state.update_data(
        source_chat_id=callback.message.chat.id,
        source_message_id=callback.message.message_id,
    )
    await send_temp_message(
        callback.message,
        "Введите <b>id шаблона</b>, который нужно открыть.\n\n"
        "Например: <code>12</code>",
    )


@router.message(SearchTemplateState.waiting_for_id)
async def templates_search_receive(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    raw = (message.text or "").strip()
    if raw == "/cancel":
        await state.clear()
        await message.answer("Поиск отменён.")
        return
    try:
        template_id = int(raw)
    except ValueError:
        await message.answer("Введите id шаблона числом, например: <code>12</code>.")
        return

    data = await state.get_data()
    await state.clear()
    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)

    if template is None or template.is_deleted:
        await send_temp_message(message, f"Шаблон с id <code>{template_id}</code> не найден или удалён.")
        return

    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if isinstance(source_chat_id, int) and isinstance(source_message_id, int):
        await clear_temp_messages(message)
        await message.bot.edit_message_text(
            chat_id=source_chat_id,
            message_id=source_message_id,
            text=_fmt_template_card(template),
            reply_markup=template_detail_menu(
                template_id=template.id,
                is_active=template.is_active,
                can_edit=_can_edit(role),
            ),
        )
        await send_temp_message(message, "<b>Текст шаблона</b>:", disable_web_page_preview=True)
        await _send_body_text(message, template.body_text)
        return

    await _show_template_message(message, template_id=template_id, role=role)


@router.callback_query(F.data.startswith("templates:open:"))
async def template_open(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)
    if template is None or template.is_deleted:
        await callback.message.answer("Шаблон не найден.")
        return

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        _fmt_template_card(template),
        reply_markup=template_detail_menu(
            template_id=template.id,
            is_active=template.is_active,
            can_edit=_can_edit(role),
        ),
    )
    await send_temp_message(callback.message, "<b>Текст шаблона</b>:", disable_web_page_preview=True)
    await _send_body_text(callback.message, template.body_text)


@router.callback_query(F.data.startswith("templates:versions:"))
async def template_versions(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)
        if template is None:
            await callback.message.answer("Шаблон не найден.")
            return
        versions = await list_versions(session, key=template.key)

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        "📚 <b>Версии шаблона</b>\n\n"
        f"{template.category} • {_ru_channel(template.channel)}/{_ru_style(template.style)} • "
        f"{_ru_case(template.case)} • {_ru_language(template.language)}",
        reply_markup=template_versions_menu(items=versions, current_id=template.id, can_edit=_can_edit(role)),
    )


@router.callback_query(F.data.startswith("templates:edit:"))
async def template_edit_start(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_edit(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)
    if template is None or template.is_deleted:
        await callback.message.answer("Шаблон не найден.")
        return

    await state.set_state(EditTemplateState.waiting_for_body)
    await state.update_data(template_id=template.id)
    await send_temp_message(
        callback.message,
        "✏️ Отправьте новый <b>текст шаблона</b> одним сообщением.\n\n"
        "Чтобы отменить — отправьте /cancel.",
    )


@router.message(EditTemplateState.waiting_for_body)
async def template_edit_receive(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_edit(role):
        await state.clear()
        await message.answer("⛔ Доступ запрещён.")
        return
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return

    data = await state.get_data()
    template_id = data.get("template_id")
    if not isinstance(template_id, int):
        await state.clear()
        await message.answer("Сценарий редактирования сброшен. Откройте шаблон заново.")
        return

    new_text = message.text or ""
    await state.clear()
    try:
        async with _sessionmaker() as session:
            template = await update_body_text(
                session,
                template_id=template_id,
                new_body_text=new_text,
                actor_tg_id=message.from_user.id if message.from_user else None,
            )
        if template is None:
            await message.answer("Шаблон не найден.")
            return
        await message.answer("✅ Текст обновлён.")
        await message.answer(
            _fmt_template_card(template),
            reply_markup=template_detail_menu(
                template_id=template.id,
                is_active=template.is_active,
                can_edit=True,
            ),
        )
        await send_temp_message(message, "<b>Текст шаблона</b>:")
        await _send_body_text(message, template.body_text)
    except (SQLAlchemyError, Exception) as exc:
        logger.exception("template edit failed: %s", exc)
        await message.answer("😔 Не удалось сохранить изменения в БД.")


@router.callback_query(F.data.startswith("templates:new_version:"))
async def template_new_version(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_edit(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        base_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    try:
        async with _sessionmaker() as session:
            template = await create_new_version(
                session,
                base_template_id=base_id,
                actor_tg_id=callback.from_user.id,
                activate_new=False,
            )
        if template is None:
            await callback.message.answer("Не удалось создать новую версию.")
            return
        await callback.message.answer(f"✅ Создана новая версия v{template.version} (id <code>{template.id}</code>).")
        await callback.message.answer(
            _fmt_template_card(template),
            reply_markup=template_detail_menu(
                template_id=template.id,
                is_active=template.is_active,
                can_edit=True,
            ),
        )
    except Exception as exc:
        logger.exception("new version failed: %s", exc)
        await callback.message.answer("😔 Не удалось создать новую версию.")


@router.callback_query(F.data.startswith("templates:active:"))
async def template_set_active(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_edit(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 4:
        return
    try:
        template_id = int(parts[2])
    except ValueError:
        return
    is_active = parts[3] == "1"

    try:
        async with _sessionmaker() as session:
            template = await toggle_active(
                session,
                template_id=template_id,
                is_active=is_active,
                actor_tg_id=callback.from_user.id,
            )
        if template is None:
            await callback.message.answer("Шаблон не найден.")
            return
        await safe_edit_text(
            callback.message,
            _fmt_template_card(template),
            reply_markup=template_detail_menu(
                template_id=template.id,
                is_active=template.is_active,
                can_edit=True,
            ),
        )
    except Exception as exc:
        logger.exception("toggle active failed: %s", exc)
        await callback.message.answer("😔 Не удалось обновить активность в БД.")


@router.callback_query(F.data.startswith("templates:delete:"))
async def template_delete_prompt(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_edit(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    await clear_temp_messages(callback.message)
    await safe_edit_text(
        callback.message,
        f"🗑 Удалить шаблон <code>{template_id}</code>?\n\n"
        "Это <b>мягкое удаление</b> (is_deleted=true).",
        reply_markup=template_delete_confirm_menu(template_id),
    )


@router.callback_query(F.data.startswith("templates:delete_confirm:"))
async def template_delete_confirm(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_edit(role):
        await callback.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
        return
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    try:
        async with _sessionmaker() as session:
            ok = await soft_delete(session, template_id=template_id, actor_tg_id=callback.from_user.id)
        if not ok:
            await callback.message.answer("Шаблон не найден или уже удалён.")
            return
        await _templates_list_page(callback, page=0, role=role)
        await callback.message.answer("✅ Шаблон удалён (мягко).")
    except Exception as exc:
        logger.exception("delete failed: %s", exc)
        await callback.message.answer("😔 Не удалось удалить шаблон.")


@router.callback_query(F.data.startswith("templates:preview:"))
async def template_preview(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        template_id = int(callback.data.split(":")[-1])
    except ValueError:
        return

    async with _sessionmaker() as session:
        template = await get_template_by_id(session, template_id)
    if template is None or template.is_deleted:
        await callback.message.answer("Шаблон не найден.")
        return

    ctx = {
        "first_name": "Иван",
        "last_name": "Иванов",
        "middle_name": "Иванович",
        "company": "TimeWise",
        "position": "инженер",
        "email": "test@example.com",
        "tg_username": "testuser",
    }
    preview = _safe_preview(template.body_text, ctx)
    await send_temp_message(callback.message, "👁 <b>Предпросмотр</b> (тестовые данные):")
    await _send_body_text(callback.message, preview)
