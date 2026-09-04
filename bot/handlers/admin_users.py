"""Управление пользователями (таблица Users) через Telegram-бот."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.users import get_by_tg_id, list_users, set_active, set_role, soft_delete_user
from db.session import get_sessionmaker
from keyboards.panels import panel_by_role
from keyboards.users import admin_users_menu, role_select_menu, user_delete_confirm_menu, user_manage_menu
from roles import UserRole

logger = logging.getLogger(__name__)

router = Router(name="admin_users_handlers")
_sessionmaker = get_sessionmaker()


def _human_db_error(e: Exception) -> str:
    msg = str(e)
    if "InsufficientPrivilegeError" in msg or "нет доступа к последовательности" in msg:
        return (
            "⛔ Ошибка прав доступа к БД.\n\n"
            "Пользователю базы не хватает прав на sequence (auto-increment id)."
        )
    if "duplicate key value violates unique constraint" in msg:
        return "⛔ Такой tg_id уже есть в базе (дубликат)."
    if "CheckViolationError" in msg and "users_role_check" in msg:
        return "⛔ Некорректная роль для БД. Выбирайте роль кнопкой (Admin/Editor/Viewer)."
    return "😔 Не удалось сохранить пользователя. Проверьте логи и попробуйте ещё раз."


class AddUserState(StatesGroup):
    waiting_for_tg_id = State()


class ManageUserState(StatesGroup):
    waiting_for_tg_id = State()


def _is_admin(role: UserRole | None) -> bool:
    return role == UserRole.ADMIN


@router.callback_query(F.data == "admin:users")
async def users_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.message is None:
        return

    text = "👥 <b>Пользователи</b>\n\nВыберите действие:"
    await callback.message.edit_text(text, reply_markup=admin_users_menu())


@router.message(Command("add_user"))
async def add_user_command(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _is_admin(role):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    await state.set_state(AddUserState.waiting_for_tg_id)
    await message.answer(
        "Введите <b>tg_id</b> пользователя (числом).\n\n"
        "Подсказка: tg_id можно узнать у @userinfobot.",
    )


@router.callback_query(F.data == "users:add")
async def add_user_from_menu(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.message is None:
        return

    await state.set_state(AddUserState.waiting_for_tg_id)
    await callback.message.edit_text(
        "Введите <b>tg_id</b> пользователя (числом).\n\n"
        "Подсказка: tg_id можно узнать у @userinfobot.",
        reply_markup=admin_users_menu(),
    )


@router.message(AddUserState.waiting_for_tg_id)
async def add_user_receive_tg_id(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _is_admin(role):
        await message.answer("⛔ Доступ только для администратора.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        tg_id = int(raw)
    except ValueError:
        await message.answer("Введите tg_id числом, например: <code>123456789</code>.")
        return

    await state.clear()
    await message.answer(
        f"Выберите роль для tg_id <code>{tg_id}</code>:",
        reply_markup=role_select_menu(tg_id),
    )


@router.callback_query(F.data == "users:cancel")
async def users_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await callback.message.edit_text(
        "👥 <b>Пользователи</b>\n\nВыберите действие:",
        reply_markup=admin_users_menu(),
    )


@router.callback_query(F.data == "users:manage")
async def users_manage_prompt(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.message is None:
        return
    await state.set_state(ManageUserState.waiting_for_tg_id)
    await callback.message.edit_text(
        "Введите <b>tg_id</b> пользователя для управления (числом).",
        reply_markup=admin_users_menu(),
    )


@router.message(ManageUserState.waiting_for_tg_id)
async def users_manage_receive_tg_id(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _is_admin(role):
        await message.answer("⛔ Доступ только для администратора.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        tg_id = int(raw)
    except ValueError:
        await message.answer("Введите tg_id числом, например: <code>123456789</code>.", reply_markup=admin_users_menu())
        return

    await state.clear()
    async with _sessionmaker() as session:
        u = await get_by_tg_id(session, tg_id)

    if u is None:
        await message.answer("Пользователь не найден в БД.", reply_markup=admin_users_menu())
        return

    text = (
        "👤 <b>Пользователь</b>\n\n"
        f"tg_id: <code>{u.tg_id}</code>\n"
        f"роль: <b>{u.role}</b>\n"
        f"активен: <b>{'да' if u.is_active else 'нет'}</b>\n"
    )
    await message.answer(text, reply_markup=user_manage_menu(tg_id=u.tg_id, is_active=bool(u.is_active)))


@router.callback_query(F.data.startswith("users:set_role:"))
async def users_set_role(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    # users:set_role:<tg_id>:<role>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    try:
        tg_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный tg_id.", show_alert=True)
        return

    new_role = UserRole.from_value(parts[3])
    if new_role is None:
        await callback.answer("Некорректная роль.", show_alert=True)
        return

    try:
        async with _sessionmaker() as session:
            user = await set_role(session, tg_id=tg_id, role=new_role.value)
    except (SQLAlchemyError, Exception) as e:
        logger.exception("Не удалось сохранить пользователя tg_id=%d: %s", tg_id, e)
        await callback.message.edit_text(
            _human_db_error(e),
            reply_markup=panel_by_role(role or UserRole.VIEWER),
        )
        return

    await callback.message.edit_text(
        "✅ Пользователь сохранён.\n\n"
        f"tg_id: <code>{user.tg_id}</code>\n"
        f"роль: <b>{user.role}</b>\n"
        f"активен: <b>{'да' if user.is_active else 'нет'}</b>",
        reply_markup=user_manage_menu(tg_id=user.tg_id, is_active=bool(user.is_active)),
    )


@router.message(Command("users"))
async def users_list_command(message: Message, role: UserRole | None = None) -> None:
    if not _is_admin(role):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    async with _sessionmaker() as session:
        users = await list_users(session)

    if not users:
        await message.answer("Список пуст. Добавьте пользователя через /add_user.")
        return

    lines = [
        "👥 <b>Пользователи (последние)</b>",
        "",
    ]
    for u in users:
        lines.append(
            f"- <code>{u.tg_id}</code> — <b>{u.role}</b> — {'активен' if u.is_active else 'не активен'}"
        )
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "users:list")
async def users_list_from_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.message is None:
        return

    async with _sessionmaker() as session:
        users = await list_users(session)

    if not users:
        await callback.message.edit_text(
            "Список пуст. Нажмите «Добавить пользователя».",
            reply_markup=admin_users_menu(),
        )
        return

    lines = [
        "👥 <b>Пользователи (последние)</b>",
        "",
    ]
    for u in users:
        lines.append(
            f"- <code>{u.tg_id}</code> — <b>{u.role}</b> — {'активен' if u.is_active else 'не активен'}"
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_users_menu())


@router.callback_query(F.data.startswith("users:set_active:"))
async def users_set_active(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        tg_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный tg_id.", show_alert=True)
        return
    is_active = parts[3] == "1"

    try:
        async with _sessionmaker() as session:
            user = await set_active(session, tg_id=tg_id, is_active=is_active)
    except (SQLAlchemyError, Exception) as e:
        logger.exception("Не удалось обновить активность tg_id=%d: %s", tg_id, e)
        await callback.message.answer(_human_db_error(e), reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    if user is None:
        await callback.message.answer("Пользователь не найден.", reply_markup=admin_users_menu())
        return

    await callback.message.edit_text(
        "✅ Обновлено.\n\n"
        f"tg_id: <code>{user.tg_id}</code>\n"
        f"роль: <b>{user.role}</b>\n"
        f"активен: <b>{'да' if user.is_active else 'нет'}</b>",
        reply_markup=user_manage_menu(tg_id=user.tg_id, is_active=bool(user.is_active)),
    )


@router.callback_query(F.data.startswith("users:delete:"))
async def users_delete_prompt(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        tg_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный tg_id.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 Удалить пользователя <code>{tg_id}</code>?\n\nЭто <b>мягкое удаление</b>: is_deleted=true, is_active=false.",
        reply_markup=user_delete_confirm_menu(tg_id),
    )


@router.callback_query(F.data.startswith("users:delete_confirm:"))
async def users_delete_confirm(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _is_admin(role):
        await callback.answer("⛔ Доступ только для администратора.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        tg_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный tg_id.", show_alert=True)
        return

    try:
        async with _sessionmaker() as session:
            ok = await soft_delete_user(session, tg_id=tg_id)
    except (SQLAlchemyError, Exception) as e:
        logger.exception("Не удалось удалить пользователя tg_id=%d: %s", tg_id, e)
        await callback.message.answer(_human_db_error(e), reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    if not ok:
        await callback.message.edit_text("Пользователь не найден.", reply_markup=admin_users_menu())
        return

    await callback.message.edit_text("✅ Пользователь удалён (мягко).", reply_markup=admin_users_menu())

