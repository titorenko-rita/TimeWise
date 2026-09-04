from __future__ import annotations

from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db.repositories.holidays import create_holiday, list_holidays
from db.session import get_sessionmaker
from keyboards.common import skip_menu
from keyboards.holidays import holiday_gender_menu, holidays_menu
from roles import UserRole

router = Router(name="holidays_handlers")
_sessionmaker = get_sessionmaker()


class AddHolidayState(StatesGroup):
    name = State()
    date_value = State()
    rrule = State()
    target_gender = State()
    category = State()


def _can_manage_holidays(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


async def _render_holidays(target: Message | CallbackQuery, *, role: UserRole | None) -> None:
    async with _sessionmaker() as session:
        holidays = await list_holidays(session)

    lines = ["🎉 <b>Праздники</b>", ""]
    if not holidays:
        lines.append("Пока нет праздников в таблице <code>holidays</code>.")
    else:
        lines.append(f"Всего записей: <b>{len(holidays)}</b>")
        lines.append("")
        for holiday in holidays[:50]:
            lines.append(
                f"- <code>{holiday.id}</code> • <b>{holiday.name}</b> • "
                f"{holiday.date.isoformat() if holiday.date else '—'} • "
                f"{holiday.rrule or '—'} • "
                f"{holiday.target_gender or 'Любой'} • "
                f"{holiday.category or '—'}"
            )

    text = "\n".join(lines)
    reply_markup = holidays_menu(role)
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        await target.message.edit_text(text, reply_markup=reply_markup)
        return
    await target.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "admin:holidays")
async def holidays_root(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_holidays(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    await _render_holidays(callback, role=role)


@router.callback_query(F.data == "holidays:add")
async def holiday_add_start(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if not _can_manage_holidays(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AddHolidayState.name)
    await callback.message.answer("Введите <b>название праздника</b>:")


@router.message(AddHolidayState.name)
async def holiday_add_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не должно быть пустым.")
        return
    await state.update_data(name=name)
    await state.set_state(AddHolidayState.date_value)
    await message.answer("Введите <b>дату</b> в формате <code>YYYY-MM-DD</code>:")


@router.message(AddHolidayState.date_value)
async def holiday_add_date(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        year, month, day = [int(part) for part in raw.split("-")]
        parsed = date(year, month, day)
    except Exception:
        await message.answer("Неверный формат даты. Пример: <code>2026-03-08</code>.")
        return
    await state.update_data(date_value=parsed)
    await state.set_state(AddHolidayState.rrule)
    await message.answer(
        "Введите <b>RRULE</b> или нажмите «Пропустить».\n"
        "Если пропустить, будет использовано <code>FREQ=YEARLY</code>.",
        reply_markup=skip_menu(skip_cb="holidays:skip"),
    )


@router.message(AddHolidayState.rrule)
async def holiday_add_rrule(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    await state.update_data(rrule=raw or "FREQ=YEARLY")
    await state.set_state(AddHolidayState.target_gender)
    await message.answer("Выберите <b>целевой пол</b>:", reply_markup=holiday_gender_menu())


@router.callback_query(F.data == "holidays:skip")
async def holiday_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    current = await state.get_state()
    if current == AddHolidayState.rrule.state:
        await state.update_data(rrule="FREQ=YEARLY")
        await state.set_state(AddHolidayState.target_gender)
        await callback.message.answer("Выберите <b>целевой пол</b>:", reply_markup=holiday_gender_menu())


@router.callback_query(F.data.startswith("holidays:gender:"))
async def holiday_add_gender(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.data is None or callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    target_gender = None if raw == "any" else raw
    await state.update_data(target_gender=target_gender)
    await state.set_state(AddHolidayState.category)
    await callback.message.answer("Введите <b>категорию</b> (например <code>Official</code> или <code>Corporate</code>):")


@router.message(AddHolidayState.category)
async def holiday_add_category(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    category = (message.text or "").strip()
    if not category:
        await message.answer("Категория не должна быть пустой.")
        return

    data = await state.get_data()
    await state.clear()

    async with _sessionmaker() as session:
        holiday = await create_holiday(
            session,
            name=data["name"],
            date_value=data["date_value"],
            rrule=data.get("rrule") or "FREQ=YEARLY",
            target_gender=data.get("target_gender"),
            category=category,
        )

    await message.answer(
        "✅ Праздник сохранён.\n\n"
        f"id: <code>{holiday.id}</code>\n"
        f"Название: <b>{holiday.name}</b>"
    )
    await _render_holidays(message, role=role)
