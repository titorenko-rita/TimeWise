"""Управление контактами (таблица Contacts) через Telegram-бот."""

from __future__ import annotations

import csv
import io
import logging
import asyncio
from datetime import date

from aiogram import F, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from openpyxl import load_workbook
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.contacts import (
    contact_exists_by_email,
    contact_exists_by_tg_chat_id,
    contact_exists_by_tg_username,
    create_contact,
    get_contact_by_id,
    import_contacts,
    list_contacts,
    soft_delete_contact,
    update_contact,
)
from db.session import get_sessionmaker
from keyboards.common import skip_cancel_menu, skip_menu
from keyboards.contacts import (
    admin_contacts_menu,
    contact_active_menu,
    contact_delete_confirm_menu,
    contact_edit_fields_menu,
    contacts_list_actions_menu,
    default_style_menu,
    default_style_edit_menu,
    gender_menu,
    preferred_channel_menu,
    preferred_channel_edit_menu,
)
from roles import UserRole
from keyboards.panels import panel_by_role

logger = logging.getLogger(__name__)

router = Router(name="admin_contacts_handlers")
_sessionmaker = get_sessionmaker()


class AddContactState(StatesGroup):
    last_name = State()
    first_name = State()
    middle_name = State()
    gender = State()
    birthday = State()
    position = State()
    company = State()
    tz = State()
    tg_username = State()
    tg_chat_id = State()
    email = State()
    preferred_channel = State()
    default_style = State()
    segment = State()
    notes = State()


class EditContactState(StatesGroup):
    waiting_for_contact_id = State()
    waiting_for_value = State()


class DeleteContactState(StatesGroup):
    waiting_for_contact_id = State()


class ContactListFilterState(StatesGroup):
    waiting_for_fio = State()
    waiting_for_company = State()
    waiting_for_position = State()


class ImportContactsState(StatesGroup):
    waiting_for_file = State()


def _can_manage_contacts(role: UserRole | None) -> bool:
    return role in {UserRole.ADMIN, UserRole.EDITOR}


def _can_delete_contacts(role: UserRole | None) -> bool:
    return role == UserRole.ADMIN


def _is_skip(text: str) -> bool:
    t = text.strip().lower()
    return t in {"-", "—", "пропустить", "skip", "нет"}


def _fmt(value: str | None) -> str:
    return value if value else "—"


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "—"


def _normalize_import_header(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _normalize_import_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_import_date(value: str) -> date:
    text = value.strip()
    for sep in ("-", ".", "/"):
        parts = text.split(sep)
        if len(parts) == 3:
            y, m, d = [int(x) for x in parts]
            return date(y, m, d)
    raise ValueError("invalid date")


def _normalize_gender(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "male": "Male",
        "m": "Male",
        "м": "Male",
        "муж": "Male",
        "мужской": "Male",
        "female": "Female",
        "f": "Female",
        "ж": "Female",
        "жен": "Female",
        "женский": "Female",
    }
    if raw not in mapping:
        raise ValueError("gender")
    return mapping[raw]


def _normalize_channel(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "telegram": "Telegram",
        "телеграм": "Telegram",
        "email": "Email",
        "mail": "Email",
        "почта": "Email",
    }
    if raw not in mapping:
        raise ValueError("channel")
    return mapping[raw]


def _normalize_style(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "friendly": "Friendly",
        "дружеский": "Friendly",
        "business": "Business",
        "деловой": "Business",
        "official": "Official",
        "официальный": "Official",
    }
    if raw not in mapping:
        raise ValueError("style")
    return mapping[raw]


def _required_import_headers() -> set[str]:
    return {
        "last_name",
        "first_name",
        "gender",
        "birthday",
        "tg_username",
        "email",
        "preferred_channel",
        "default_style",
    }


def _build_import_template_text() -> str:
    return (
        "Загрузите файл <b>CSV</b> или <b>XLSX</b> с колонками:\n\n"
        "<code>last_name, first_name, middle_name, gender, birthday, position, company, tz, "
        "tg_chat_id, "
        "tg_username, email, preferred_channel, default_style, segment, notes, is_active</code>\n\n"
        "Обязательные колонки:\n"
        "<code>last_name, first_name, gender, birthday, tg_username, email, preferred_channel, default_style</code>\n\n"
        "Примеры значений:\n"
        "- <code>gender</code>: Male / Female / М / Ж\n"
        "- <code>birthday</code>: 1999-12-31\n"
        "- <code>preferred_channel</code>: Telegram / Email\n"
        "- <code>default_style</code>: Friendly / Business / Official"
    )


def _parse_csv_bytes(file_bytes: bytes) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            text = file_bytes.decode(encoding)
            reader = csv.DictReader(io.StringIO(text), delimiter="," if "," in text else ";")
            return [{_normalize_import_header(k): _normalize_import_value(v) for k, v in row.items()} for row in reader]
        except Exception as e:
            last_error = e
    raise ValueError(f"Не удалось прочитать CSV: {last_error}")


def _parse_xlsx_bytes(file_bytes: bytes) -> list[dict[str, str]]:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = next(rows_iter, None)
    if not headers:
        return []
    normalized_headers = [_normalize_import_header(h) for h in headers]
    rows: list[dict[str, str]] = []
    for values in rows_iter:
        rows.append(
            {
                normalized_headers[idx]: _normalize_import_value(values[idx] if idx < len(values) else "")
                for idx in range(len(normalized_headers))
            }
        )
    return rows


def _map_import_rows(raw_rows: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    mapped_rows: list[dict] = []
    errors: list[str] = []
    required = _required_import_headers()

    for idx, row in enumerate(raw_rows, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        missing = [name for name in required if not row.get(name)]
        if missing:
            errors.append(f"Строка {idx}: нет колонок/значений {', '.join(missing)}")
            continue
        try:
            mapped_rows.append(
                {
                    "last_name": row["last_name"],
                    "first_name": row["first_name"],
                    "middle_name": row.get("middle_name", ""),
                    "gender": _normalize_gender(row["gender"]),
                    "birthday": _parse_import_date(row["birthday"]),
                    "position": row.get("position", ""),
                    "company": row.get("company", ""),
                    "tz": row.get("tz") or None,
                    "tg_chat_id": int(row["tg_chat_id"]) if row.get("tg_chat_id") else None,
                    "tg_username": row["tg_username"].lstrip("@"),
                    "email": row["email"],
                    "preferred_channel": _normalize_channel(row["preferred_channel"]),
                    "default_style": _normalize_style(row["default_style"]),
                    "segment": row.get("segment") or None,
                    "notes": row.get("notes") or None,
                    "is_active": (row.get("is_active") or "1").strip().lower() not in {"0", "false", "нет", "no"},
                    "is_deleted": False,
                }
            )
        except ValueError as e:
            errors.append(f"Строка {idx}: некорректное значение поля {e}")
    return mapped_rows, errors


async def _download_import_file(message: Message) -> tuple[str, bytes]:
    if message.document is None:
        raise ValueError("Документ не найден.")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            buffer = io.BytesIO()
            await message.bot.download(message.document, destination=buffer)
            filename = message.document.file_name or "contacts_import"
            return filename, buffer.getvalue()
        except TelegramNetworkError as e:
            last_error = e
            if attempt < 3:
                await asyncio.sleep(1)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise ValueError("Не удалось скачать документ.")


def _contact_summary(data: dict) -> str:
    return (
        "📇 <b>Новый контакт</b>\n\n"
        f"Фамилия: <b>{data.get('last_name')}</b>\n"
        f"Имя: <b>{data.get('first_name')}</b>\n"
        f"Отчество: <b>{_fmt(data.get('middle_name'))}</b>\n"
        f"Пол: <b>{_fmt(data.get('gender'))}</b>\n"
        f"ДР: <b>{_fmt_date(data.get('birthday'))}</b>\n"
        f"Должность: <b>{_fmt(data.get('position'))}</b>\n"
        f"Компания: <b>{_fmt(data.get('company'))}</b>\n"
        f"Часовой пояс: <b>{_fmt(data.get('tz'))}</b>\n"
        f"tg_username: <b>{_fmt(data.get('tg_username'))}</b>\n"
        f"tg_chat_id: <b>{_fmt(str(data.get('tg_chat_id')) if data.get('tg_chat_id') is not None else None)}</b>\n"
        f"email: <b>{_fmt(data.get('email'))}</b>\n"
        f"Канал: <b>{_fmt(data.get('preferred_channel'))}</b>\n"
        f"Стиль: <b>{_fmt(data.get('default_style'))}</b>\n"
        f"Сегмент: <b>{_fmt(data.get('segment'))}</b>\n"
        f"Заметка: <b>{_fmt(data.get('notes'))}</b>\n"
    )


def _contact_card(contact) -> str:
    return (
        f"📇 <b>Контакт</b> <code>{contact.id}</code>\n\n"
        f"Фамилия: <b>{contact.last_name}</b>\n"
        f"Имя: <b>{contact.first_name}</b>\n"
        f"Отчество: <b>{_fmt(contact.middle_name)}</b>\n"
        f"Пол: <b>{_fmt(contact.gender)}</b>\n"
        f"ДР: <b>{_fmt_date(contact.birthday)}</b>\n"
        f"Должность: <b>{_fmt(contact.position)}</b>\n"
        f"Компания: <b>{_fmt(contact.company)}</b>\n"
        f"Часовой пояс: <b>{_fmt(contact.tz)}</b>\n"
        f"tg_username: <b>{_fmt(contact.tg_username)}</b>\n"
        f"tg_chat_id: <b>{_fmt(str(contact.tg_chat_id) if getattr(contact, 'tg_chat_id', None) is not None else None)}</b>\n"
        f"email: <b>{_fmt(contact.email)}</b>\n"
        f"Канал: <b>{_fmt(contact.preferred_channel)}</b>\n"
        f"Стиль: <b>{_fmt(contact.default_style)}</b>\n"
        f"Сегмент: <b>{_fmt(contact.segment)}</b>\n"
        f"Заметка: <b>{_fmt(contact.notes)}</b>\n"
        f"Активен: <b>{'да' if contact.is_active else 'нет'}</b>\n"
    )


def _filters_summary(*, fio_query: str | None, company: str | None, position: str | None) -> str:
    parts: list[str] = []
    if fio_query:
        parts.append(f"ФИО: <b>{fio_query}</b>")
    if company:
        parts.append(f"Компания: <b>{company}</b>")
    if position:
        parts.append(f"Должность: <b>{position}</b>")
    return "\n".join(parts)


async def _render_contacts_list(
    target: Message | CallbackQuery,
    *,
    role: UserRole | None,
    fio_query: str | None = None,
    company: str | None = None,
    position: str | None = None,
) -> None:
    async with _sessionmaker() as session:
        contacts = await list_contacts(session, fio_query=fio_query, company=company, position=position)

    has_filters = any([fio_query, company, position])
    lines = ["📇 <b>Контакты</b>", ""]
    if has_filters:
        lines.append("<b>Фильтры</b>")
        lines.append(_filters_summary(fio_query=fio_query, company=company, position=position))
        lines.append("")

    if not contacts:
        lines.append("По заданным условиям контакты не найдены.")
    else:
        lines.append("<b>Список</b>")
        lines.append("")
        for c in contacts:
            lines.append(
                f"- <code>{c.id}</code> — {c.last_name} {c.first_name} — "
                f"{_fmt(c.company)} / {_fmt(c.position)} / {(c.preferred_channel or '—')}"
            )

    text = "\n".join(lines)
    reply_markup = contacts_list_actions_menu(has_filters=has_filters, role=role)
    if isinstance(target, CallbackQuery):
        if target.message is None:
            return
        await target.message.edit_text(text, reply_markup=reply_markup)
        return
    await target.answer(text, reply_markup=reply_markup)


def _human_db_error(e: Exception) -> str:
    msg = str(e)
    if "InsufficientPrivilegeError" in msg or "нет доступа к последовательности" in msg:
        return (
            "⛔ Ошибка прав доступа к БД.\n\n"
            "Пользователю базы не хватает прав на sequence (auto-increment id).\n"
            "Нужно выдать права на последовательности в Postgres (например `contacts_id_seq`)."
        )
    if "contacts_tg_username_unique" in msg:
        return "⚠ Такой tg_username уже есть в базе. Введите другой username."
    if "contacts_email_unique" in msg:
        return "⚠ Такой email уже есть в базе. Введите другой email."
    if "tg_chat_id" in msg and "unique" in msg.lower():
        return "⚠ Такой tg_chat_id уже есть в базе. Введите другой tg id."
    if "duplicate key value violates unique constraint" in msg:
        return "⛔ Дубликат. Похоже, такой контакт (email/username) уже существует."
    if "CheckViolationError" in msg and "contacts_default_style_check" in msg:
        return "⛔ Некорректный стиль. Выберите стиль кнопкой (Дружеский/Деловой/Официальный)."
    if "CheckViolationError" in msg and "contacts_preferred_channel_check" in msg:
        return "⛔ Некорректный канал. Выберите канал кнопкой (Telegram/Email)."
    if "CheckViolationError" in msg and "contacts_gender_check" in msg:
        return "⛔ Некорректный пол. Выберите пол кнопкой (М/Ж)."
    return "😔 Не удалось сохранить. Проверьте данные и попробуйте ещё раз."


async def _send_main_menu(message: Message, role: UserRole | None) -> None:
    await message.answer("Выберите раздел:", reply_markup=panel_by_role(role or UserRole.VIEWER))


@router.callback_query(F.data == "admin:contacts")
async def contacts_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return

    await callback.message.edit_text(
        "📇 <b>Контакты</b>\n\nВыберите действие:",
        reply_markup=admin_contacts_menu(role),
    )


@router.callback_query(F.data == "contacts:cancel")
async def contacts_cancel(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await callback.message.edit_text(
        "📇 <b>Контакты</b>\n\nВыберите действие:",
        reply_markup=admin_contacts_menu(role),
    )


@router.message(Command("import_contacts"))
async def import_contacts_command(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Эта команда доступна только Admin/Editor.")
        return
    await state.clear()
    await state.set_state(ImportContactsState.waiting_for_file)
    await message.answer(_build_import_template_text(), reply_markup=admin_contacts_menu(role))


@router.callback_query(F.data == "contacts:import")
async def import_contacts_from_menu(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return
    await state.clear()
    await state.set_state(ImportContactsState.waiting_for_file)
    await callback.message.edit_text(_build_import_template_text(), reply_markup=admin_contacts_menu(role))


@router.message(ImportContactsState.waiting_for_file)
async def import_contacts_receive_file(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Эта команда доступна только Admin/Editor.")
        await state.clear()
        return
    if message.document is None:
        await message.answer("Пришлите файл в формате CSV или XLSX.")
        return

    try:
        filename, file_bytes = await _download_import_file(message)
        lower_name = filename.lower()
        if lower_name.endswith(".csv"):
            raw_rows = _parse_csv_bytes(file_bytes)
        elif lower_name.endswith(".xlsx"):
            raw_rows = _parse_xlsx_bytes(file_bytes)
        else:
            await message.answer("Поддерживаются только файлы CSV и XLSX.")
            return

        if not raw_rows:
            await message.answer("Файл пустой или в нём нет строк для импорта.")
            return

        headers = set(raw_rows[0].keys())
        missing_headers = sorted(_required_import_headers() - headers)
        if missing_headers:
            await message.answer(
                "В файле не хватает обязательных колонок:\n"
                f"<code>{', '.join(missing_headers)}</code>"
            )
            return

        mapped_rows, mapping_errors = _map_import_rows(raw_rows)
        async with _sessionmaker() as session:
            result = await import_contacts(session, mapped_rows)

        await state.clear()

        lines = [
            "📥 <b>Импорт контактов завершён</b>",
            "",
            f"Файл: <code>{filename}</code>",
            f"Строк обработано: <b>{len(raw_rows)}</b>",
            f"Успешно импортировано: <b>{result.imported}</b>",
            f"Ошибок валидации: <b>{len(mapping_errors)}</b>",
            f"Ошибок сохранения: <b>{result.failed}</b>",
        ]
        details = (mapping_errors + result.errors)[:15]
        if details:
            lines.extend(["", "<b>Проблемные строки</b>"])
            lines.extend(f"- {detail}" for detail in details)
        await message.answer("\n".join(lines), reply_markup=panel_by_role(role or UserRole.VIEWER))
    except Exception as e:
        logger.exception("Не удалось импортировать контакты: %s", e)
        if isinstance(e, TelegramNetworkError):
            await message.answer(
                "😔 Не удалось скачать файл из Telegram из-за сетевой ошибки.\n"
                "Попробуйте отправить файл ещё раз, когда соединение станет стабильнее."
            )
            return
        await message.answer("😔 Не удалось обработать файл импорта. Проверьте формат CSV/XLSX и попробуйте ещё раз.")


@router.message(Command("add_contact"))
async def add_contact_command(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Эта команда доступна только Admin/Editor.")
        return
    await state.clear()
    await state.set_state(AddContactState.last_name)
    await message.answer(
        "Введите <b>фамилию</b> контакта.\n\n"
        "Для некоторых полей можно написать <code>пропустить</code> или <code>-</code>."
    )


@router.callback_query(F.data == "contacts:add")
async def add_contact_from_menu(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return

    await state.clear()
    await state.set_state(AddContactState.last_name)
    await callback.message.edit_text("Введите <b>фамилию</b> контакта:")


@router.message(AddContactState.last_name)
async def add_contact_last_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Фамилия не может быть пустой. Введите фамилию.")
        return
    await state.update_data(last_name=text)
    await state.set_state(AddContactState.first_name)
    await message.answer("Введите <b>имя</b> контакта:")


@router.message(AddContactState.first_name)
async def add_contact_first_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Имя не может быть пустым. Введите имя.")
        return
    await state.update_data(first_name=text)
    await state.set_state(AddContactState.middle_name)
    await message.answer(
        "Введите <b>отчество</b> (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.middle_name)
async def add_contact_middle_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(middle_name="" if _is_skip(text) else text)
    await state.set_state(AddContactState.gender)
    await message.answer("Выберите <b>пол</b>:", reply_markup=gender_menu())


@router.callback_query(F.data.startswith("contacts:gender:"))
async def add_contact_gender(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.data is None or callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    await state.update_data(gender=raw)  # Male/Female (как в CHECK)
    await state.set_state(AddContactState.birthday)
    await callback.message.edit_text("Введите <b>дату рождения</b> в формате <code>YYYY-MM-DD</code>:")


@router.message(AddContactState.birthday)
async def add_contact_birthday(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if _is_skip(text):
        await message.answer("Дата рождения обязательна. Пример: <code>1999-12-31</code>.")
        return
    try:
        y, m, d = [int(x) for x in text.split("-")]
        await state.update_data(birthday=date(y, m, d))
    except Exception:
        await message.answer("Неверный формат. Пример: <code>1999-12-31</code>.")
        return
    await state.set_state(AddContactState.position)
    await message.answer(
        "Введите <b>должность</b> (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.position)
async def add_contact_position(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(position="" if _is_skip(text) else text)
    await state.set_state(AddContactState.company)
    await message.answer(
        "Введите <b>компанию</b> (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.company)
async def add_contact_company(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(company="" if _is_skip(text) else text)
    await state.set_state(AddContactState.tz)
    await message.answer(
        "Введите <b>часовой пояс</b> (например <code>Europe/Moscow</code>) (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.tz)
async def add_contact_tz(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(tz=None if _is_skip(text) else text)
    await state.set_state(AddContactState.tg_username)
    await message.answer("Введите <b>tg_username</b> (без @):")


@router.message(AddContactState.tg_username)
async def add_contact_tg_username(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if _is_skip(text):
        await message.answer("tg_username обязателен. Введите значение (например <code>someuser</code>).")
        return
    value = text.lstrip("@")
    async with _sessionmaker() as session:
        if await contact_exists_by_tg_username(session, value):
            await message.answer(
                "⚠ Контакт с таким <b>tg_username</b> уже существует.\n"
                "Введите другой username."
            )
            return
    await state.update_data(tg_username=value)
    await state.set_state(AddContactState.tg_chat_id)
    await message.answer(
        "Введите <b>tg_chat_id</b> (числовой id Telegram) или нажмите «Пропустить»:",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.tg_chat_id)
async def add_contact_tg_chat_id(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if _is_skip(text):
        await state.update_data(tg_chat_id=None)
        await state.set_state(AddContactState.email)
        await message.answer("Введите <b>email</b>:")
        return

    try:
        value = int(text)
    except ValueError:
        await message.answer("Введите числовой <b>tg_chat_id</b> или нажмите «Пропустить».")
        return

    async with _sessionmaker() as session:
        if await contact_exists_by_tg_chat_id(session, value):
            await message.answer(
                "⚠ Контакт с таким <b>tg_chat_id</b> уже существует.\n"
                "Введите другой tg id."
            )
            return

    await state.update_data(tg_chat_id=value)
    await state.set_state(AddContactState.email)
    await message.answer("Введите <b>email</b>:")


@router.message(AddContactState.email)
async def add_contact_email(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if _is_skip(text):
        await message.answer("Email обязателен. Введите email.")
        return
    async with _sessionmaker() as session:
        if await contact_exists_by_email(session, text):
            await message.answer(
                "⚠ Контакт с таким <b>email</b> уже существует.\n"
                "Введите другой email."
            )
            return
    await state.update_data(email=text)
    await state.set_state(AddContactState.preferred_channel)
    await message.answer("Выберите <b>канал связи</b>:", reply_markup=preferred_channel_menu())


@router.callback_query(F.data.startswith("contacts:channel:"))
async def add_contact_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.data is None or callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    await state.update_data(preferred_channel=raw)  # Telegram/Email (SMS скрыт в UI)
    await state.set_state(AddContactState.default_style)
    await callback.message.edit_text("Выберите <b>стиль</b>:", reply_markup=default_style_menu())


@router.callback_query(F.data.startswith("contacts:style:"))
async def add_contact_style(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.data is None or callback.message is None:
        return
    raw = callback.data.split(":")[-1]
    await state.update_data(default_style=raw)  # Friendly/Business/Official (как в CHECK)
    await state.set_state(AddContactState.segment)
    await callback.message.edit_text(
        "Введите <b>сегмент</b> (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.segment)
async def add_contact_segment(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.update_data(segment=None if _is_skip(text) else text)
    await state.set_state(AddContactState.notes)
    await message.answer(
        "Введите <b>заметку</b> (необязательно):",
        reply_markup=skip_menu(skip_cb="contacts:skip"),
    )


@router.message(AddContactState.notes)
async def add_contact_notes(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    text = (message.text or "").strip()
    await state.update_data(notes=None if _is_skip(text) else text)

    data = await state.get_data()
    await state.clear()

    try:
        async with _sessionmaker() as session:
            if not data.get("gender") or not data.get("preferred_channel") or not data.get("default_style"):
                await message.answer(
                    "Сценарий добавления контакта повреждён (не выбран пол/канал/стиль). Начните заново.",
                    reply_markup=panel_by_role(role or UserRole.VIEWER),
                )
                return
            contact = await create_contact(
                session,
                last_name=data["last_name"],
                first_name=data["first_name"],
                middle_name=data.get("middle_name") or "",
                gender=data["gender"],
                birthday=data["birthday"],
                position=data.get("position") or "",
                company=data.get("company") or "",
                tz=data.get("tz"),
                tg_username=data.get("tg_username") or "",
                tg_chat_id=data.get("tg_chat_id"),
                email=data.get("email") or "",
                preferred_channel=data["preferred_channel"],
                default_style=data["default_style"],
                segment=data.get("segment"),
                notes=data.get("notes"),
                is_active=True,
                is_deleted=False,
            )
    except (SQLAlchemyError, Exception) as e:
        logger.exception("Не удалось создать контакт: %s", e)
        await message.answer(_human_db_error(e), reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    await message.answer(
        "✅ Контакт сохранён.\n\n"
        f"id: <code>{contact.id}</code>\n"
        f"{contact.last_name} {contact.first_name}",
    )
    await _send_main_menu(message, role)


@router.callback_query(F.data == "contacts:skip")
async def contacts_skip(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None:
        return

    current = await state.get_state()
    if current == AddContactState.middle_name.state:
        await state.update_data(middle_name="")
        await state.set_state(AddContactState.gender)
        await callback.message.answer("Выберите <b>пол</b>:", reply_markup=gender_menu())
        return

    if current == AddContactState.position.state:
        await state.update_data(position="")
        await state.set_state(AddContactState.company)
        await callback.message.answer("Введите <b>компанию</b> (необязательно):", reply_markup=skip_menu(skip_cb="contacts:skip"))
        return

    if current == AddContactState.company.state:
        await state.update_data(company="")
        await state.set_state(AddContactState.tz)
        await callback.message.answer(
            "Введите <b>часовой пояс</b> (например <code>Europe/Moscow</code>) (необязательно):",
            reply_markup=skip_menu(skip_cb="contacts:skip"),
        )
        return

    if current == AddContactState.tz.state:
        await state.update_data(tz=None)
        await state.set_state(AddContactState.tg_username)
        await callback.message.answer("Введите <b>tg_username</b> (без @):")
        return

    if current == AddContactState.tg_chat_id.state:
        await state.update_data(tg_chat_id=None)
        await state.set_state(AddContactState.email)
        await callback.message.answer("Введите <b>email</b>:")
        return

    if current == AddContactState.segment.state:
        await state.update_data(segment=None)
        await state.set_state(AddContactState.notes)
        await callback.message.answer("Введите <b>заметку</b> (необязательно):", reply_markup=skip_menu(skip_cb="contacts:skip"))
        return

    if current == AddContactState.notes.state:
        await state.update_data(notes=None)
        # повторяем финализацию (как в add_contact_notes)
        data = await state.get_data()
        await state.clear()
        if not data.get("gender") or not data.get("preferred_channel") or not data.get("default_style"):
            await callback.message.answer(
                "Сценарий добавления контакта повреждён (не выбран пол/канал/стиль). Начните заново.",
                reply_markup=panel_by_role(role or UserRole.VIEWER),
            )
            return
        try:
            async with _sessionmaker() as session:
                contact = await create_contact(
                    session,
                    last_name=data["last_name"],
                    first_name=data["first_name"],
                    middle_name=data.get("middle_name") or "",
                    gender=data["gender"],
                    birthday=data["birthday"],
                    position=data.get("position") or "",
                    company=data.get("company") or "",
                    tz=data.get("tz"),
                    tg_username=data.get("tg_username") or "",
                    tg_chat_id=data.get("tg_chat_id"),
                    email=data.get("email") or "",
                    preferred_channel=data["preferred_channel"],
                    default_style=data["default_style"],
                    segment=data.get("segment"),
                    notes=None,
                    is_active=True,
                    is_deleted=False,
                )
        except (SQLAlchemyError, Exception) as e:
            logger.exception("Не удалось создать контакт: %s", e)
            await callback.message.answer(_human_db_error(e), reply_markup=panel_by_role(role or UserRole.VIEWER))
            return

        await callback.message.answer(
            "✅ Контакт сохранён.\n\n"
            f"id: <code>{contact.id}</code>\n"
            f"{contact.last_name} {contact.first_name}",
        )
        await callback.message.answer("Выберите раздел:", reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    await callback.message.answer("Сценарий пропуска неактуален. Откройте «Контакты» и начните заново.")


@router.message(Command("contacts"))
async def contacts_list_command(message: Message, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Эта команда доступна только Admin/Editor.")
        return
    await _render_contacts_list(message, role=role)


@router.callback_query(F.data == "contacts:list")
async def contacts_list_from_menu(callback: CallbackQuery, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return
    await _render_contacts_list(callback, role=role)


@router.callback_query(F.data == "contacts:list_reset")
async def contacts_list_reset(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    await state.clear()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    await _render_contacts_list(callback, role=role)


@router.callback_query(F.data.startswith("contacts:list_filter:"))
async def contacts_list_filter_prompt(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.data is None or callback.message is None:
        return
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return

    filter_key = callback.data.split(":")[-1]
    if filter_key == "fio":
        await state.set_state(ContactListFilterState.waiting_for_fio)
        await callback.message.answer("Введите ФИО или его часть для поиска:")
        return
    if filter_key == "company":
        await state.set_state(ContactListFilterState.waiting_for_company)
        await callback.message.answer("Введите компанию или ее часть для фильтра:")
        return
    if filter_key == "position":
        await state.set_state(ContactListFilterState.waiting_for_position)
        await callback.message.answer("Введите должность или ее часть для фильтра:")
        return


@router.message(ContactListFilterState.waiting_for_fio)
async def contacts_filter_fio(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query:
        await message.answer("Введите ФИО или часть ФИО.")
        return
    await _render_contacts_list(message, role=role, fio_query=query)


@router.message(ContactListFilterState.waiting_for_company)
async def contacts_filter_company(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query:
        await message.answer("Введите компанию или часть названия компании.")
        return
    await _render_contacts_list(message, role=role, company=query)


@router.message(ContactListFilterState.waiting_for_position)
async def contacts_filter_position(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query:
        await message.answer("Введите должность или часть должности.")
        return
    await _render_contacts_list(message, role=role, position=query)


@router.message(Command("edit_contact"))
async def edit_contact_command(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Эта команда доступна только Admin/Editor.")
        return

    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) == 2:
        try:
            contact_id = int(raw[1])
        except ValueError:
            await message.answer("Введите id контакта числом, например: <code>/edit_contact 12</code>.")
            return
        async with _sessionmaker() as session:
            contact = await get_contact_by_id(session, contact_id)
        if contact is None:
            await message.answer("Контакт не найден.")
            return
        await state.clear()
        await state.update_data(contact_id=contact_id)
        await message.answer(
            _contact_card(contact) + "\nВыберите поле для редактирования:",
            reply_markup=contact_edit_fields_menu(contact_id),
        )
        return

    await state.clear()
    await state.set_state(EditContactState.waiting_for_contact_id)
    await message.answer("Введите <b>id</b> контакта для редактирования:", reply_markup=admin_contacts_menu(role))


@router.callback_query(F.data == "contacts:edit")
async def edit_contact_from_menu(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.message is None:
        return
    await state.clear()
    await state.set_state(EditContactState.waiting_for_contact_id)
    await callback.message.edit_text("Введите <b>id</b> контакта для редактирования:", reply_markup=admin_contacts_menu(role))


@router.message(EditContactState.waiting_for_contact_id)
async def edit_contact_receive_id(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Доступ только для Admin/Editor.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        contact_id = int(raw)
    except ValueError:
        await message.answer("Введите id контакта числом, например: <code>12</code>.")
        return

    async with _sessionmaker() as session:
        contact = await get_contact_by_id(session, contact_id)
    if contact is None:
        await message.answer("Контакт не найден. Проверьте id и попробуйте ещё раз.")
        return

    await state.update_data(contact_id=contact_id)
    await message.answer(
        _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.callback_query(F.data.startswith("contacts:edit_field:"))
async def edit_contact_choose_field(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    # contacts:edit_field:<contact_id>:<field>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        contact_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный id контакта.", show_alert=True)
        return
    field = parts[3]

    await state.update_data(contact_id=contact_id, field=field)

    if field == "preferred_channel":
        await callback.message.edit_text(
            "Выберите <b>канал связи</b>:",
            reply_markup=preferred_channel_edit_menu(contact_id),
        )
        return
    if field == "default_style":
        await callback.message.edit_text(
            "Выберите <b>стиль</b>:",
            reply_markup=default_style_edit_menu(contact_id),
        )
        return
    if field == "is_active":
        await callback.message.edit_text(
            "Выберите <b>активность</b>:",
            reply_markup=contact_active_menu(contact_id),
        )
        return

    await state.set_state(EditContactState.waiting_for_value)
    field_human = {
        "last_name": "фамилию",
        "first_name": "имя",
        "middle_name": "отчество",
        "birthday": "дату рождения (YYYY-MM-DD)",
        "tz": "часовой пояс (например Europe/Moscow)",
        "tg_username": "tg_username (без @)",
        "tg_chat_id": "tg_chat_id",
        "email": "email",
        "segment": "сегмент",
        "notes": "заметку",
    }.get(field, field)
    kb = None
    if field in {"middle_name", "position", "company", "tz", "tg_chat_id", "segment", "notes"}:
        kb = skip_cancel_menu(skip_cb="contacts:skip_value", cancel_cb="contacts:cancel")
    await callback.message.answer(
        f"Введите новое значение для <b>{field_human}</b>:",
        reply_markup=kb,
    )


@router.callback_query(F.data == "contacts:skip_value")
async def contacts_skip_value(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    contact_id = data.get("contact_id")
    field = data.get("field")
    if not isinstance(contact_id, int) or not isinstance(field, str):
        await callback.message.answer("Сценарий редактирования сброшен. Откройте «Контакты» и начните заново.")
        return

    if field in {"tz", "tg_chat_id", "segment", "notes"}:
        value: object = None
    elif field in {"middle_name", "position", "company"}:
        value = ""
    else:
        await callback.message.answer("Это поле нельзя пропустить.", reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    try:
        async with _sessionmaker() as session:
            contact = await update_contact(session, contact_id, **{field: value})
    except Exception as e:
        logger.exception("Не удалось обновить контакт %s (%s): %s", contact_id, field, e)
        await callback.message.answer("😔 Не удалось сохранить изменения.", reply_markup=panel_by_role(role or UserRole.VIEWER))
        return

    if contact is None:
        await callback.message.answer("Контакт не найден.")
        return

    await state.set_state(EditContactState.waiting_for_contact_id)
    await callback.message.answer(
        "✅ Изменения сохранены.\n\n" + _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.callback_query(F.data.startswith("contacts:edit_channel:"))
async def edit_contact_set_channel(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    # contacts:edit_channel:<contact_id>:<value>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        contact_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный id.", show_alert=True)
        return
    raw_value = parts[3]
    value = raw_value  # Telegram/Email (SMS скрыт в UI)

    try:
        async with _sessionmaker() as session:
            contact = await update_contact(session, contact_id, preferred_channel=value)
    except Exception as e:
        logger.exception("Не удалось обновить канал контакта %s: %s", contact_id, e)
        await callback.message.answer("😔 Не удалось сохранить изменения. Проверьте данные и попробуйте ещё раз.")
        return

    if contact is None:
        await callback.message.answer("Контакт не найден.")
        return

    await state.set_state(EditContactState.waiting_for_contact_id)
    await callback.message.edit_text(
        _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.callback_query(F.data.startswith("contacts:edit_style:"))
async def edit_contact_set_style(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    # contacts:edit_style:<contact_id>:<value>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        contact_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный id.", show_alert=True)
        return
    raw_value = parts[3]
    value = raw_value  # Friendly/Business/Official

    try:
        async with _sessionmaker() as session:
            contact = await update_contact(session, contact_id, default_style=value)
    except Exception as e:
        logger.exception("Не удалось обновить стиль контакта %s: %s", contact_id, e)
        await callback.message.answer("😔 Не удалось сохранить изменения. Проверьте данные и попробуйте ещё раз.")
        return

    if contact is None:
        await callback.message.answer("Контакт не найден.")
        return

    await state.set_state(EditContactState.waiting_for_contact_id)
    await callback.message.edit_text(
        _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.callback_query(F.data.startswith("contacts:set_active:"))
async def edit_contact_set_active(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_manage_contacts(role):
        await callback.answer("⛔ Доступ только для Admin/Editor.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    # contacts:set_active:<contact_id>:<0|1>
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        contact_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный id.", show_alert=True)
        return
    is_active = parts[3] == "1"

    try:
        async with _sessionmaker() as session:
            contact = await update_contact(session, contact_id, is_active=is_active)
    except Exception as e:
        logger.exception("Не удалось обновить активность контакта %s: %s", contact_id, e)
        await callback.message.answer("😔 Не удалось сохранить изменения. Попробуйте ещё раз.")
        return

    if contact is None:
        await callback.message.answer("Контакт не найден.")
        return

    await state.set_state(EditContactState.waiting_for_contact_id)
    await callback.message.edit_text(
        _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.message(EditContactState.waiting_for_value)
async def edit_contact_receive_value(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_manage_contacts(role):
        await message.answer("⛔ Доступ только для Admin/Editor.")
        await state.clear()
        return

    data = await state.get_data()
    contact_id = data.get("contact_id")
    field = data.get("field")
    if not isinstance(contact_id, int) or not isinstance(field, str):
        await state.clear()
        await message.answer("Сценарий редактирования сброшен. Откройте «Контакты» и начните заново.")
        return

    raw = (message.text or "").strip()
    value: object
    if _is_skip(raw):
        if field in {"tz", "tg_chat_id", "segment", "notes"}:
            value = None
        elif field in {"middle_name", "position", "company"}:
            value = ""
        else:
            await message.answer("Это поле обязательное и не может быть пустым. Введите значение.")
            return
    else:
        value = raw

    if field in {"last_name", "first_name"}:
        if not value:
            await message.answer("Значение не может быть пустым. Введите текст.")
            return
    elif field == "birthday":
        try:
            y, m, d = [int(x) for x in str(value).split("-")]
            value = date(y, m, d)
        except Exception:
            await message.answer("Неверный формат. Пример: <code>1999-12-31</code>.")
            return
    elif field == "tg_username":
        value = str(value).lstrip("@")
    elif field == "tg_chat_id":
        try:
            value = int(str(value))
        except ValueError:
            await message.answer("Введите числовой <b>tg_chat_id</b> или нажмите «Пропустить».")
            return

    if field == "tg_username":
        async with _sessionmaker() as session:
            if await contact_exists_by_tg_username(session, str(value), exclude_contact_id=contact_id):
                await message.answer("⚠ Такой tg_username уже есть в базе. Введите другой username.")
                return
    elif field == "tg_chat_id" and value is not None:
        async with _sessionmaker() as session:
            if await contact_exists_by_tg_chat_id(session, int(value), exclude_contact_id=contact_id):
                await message.answer("⚠ Такой tg_chat_id уже есть в базе. Введите другой tg id.")
                return
    elif field == "email":
        async with _sessionmaker() as session:
            if await contact_exists_by_email(session, str(value), exclude_contact_id=contact_id):
                await message.answer("⚠ Такой email уже есть в базе. Введите другой email.")
                return

    try:
        async with _sessionmaker() as session:
            contact = await update_contact(session, contact_id, **{field: value})
    except Exception as e:
        logger.exception("Не удалось обновить контакт %s (%s): %s", contact_id, field, e)
        await message.answer("😔 Не удалось сохранить изменения. Проверьте данные и попробуйте ещё раз.")
        return

    if contact is None:
        await state.clear()
        await message.answer("Контакт не найден.")
        return

    await state.set_state(EditContactState.waiting_for_contact_id)
    await message.answer(
        "✅ Изменения сохранены.\n\n" + _contact_card(contact) + "\nВыберите поле для редактирования:",
        reply_markup=contact_edit_fields_menu(contact_id),
    )


@router.message(Command("delete_contact"))
async def delete_contact_command(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_delete_contacts(role):
        await message.answer("⛔ Удаление доступно только Admin.")
        return

    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) == 2:
        try:
            contact_id = int(raw[1])
        except ValueError:
            await message.answer("Введите id контакта числом, например: <code>/delete_contact 12</code>.")
            return
        async with _sessionmaker() as session:
            contact = await get_contact_by_id(session, contact_id)
        if contact is None:
            await message.answer("Контакт не найден.")
            return
        await state.clear()
        await state.update_data(contact_id=contact_id)
        await message.answer(
            _contact_card(contact) + "\n<b>Удалить этот контакт?</b> (мягкое удаление)",
            reply_markup=contact_delete_confirm_menu(contact_id),
        )
        return

    await state.clear()
    await state.set_state(DeleteContactState.waiting_for_contact_id)
    await message.answer("Введите <b>id</b> контакта для удаления:", reply_markup=admin_contacts_menu(role))


@router.callback_query(F.data == "contacts:delete")
async def delete_contact_from_menu(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_delete_contacts(role):
        await callback.answer("⛔ Удаление доступно только Admin.", show_alert=True)
        return
    if callback.message is None:
        return
    await state.clear()
    await state.set_state(DeleteContactState.waiting_for_contact_id)
    await callback.message.edit_text("Введите <b>id</b> контакта для удаления:", reply_markup=admin_contacts_menu(role))


@router.message(DeleteContactState.waiting_for_contact_id)
async def delete_contact_receive_id(message: Message, state: FSMContext, role: UserRole | None = None) -> None:
    if not _can_delete_contacts(role):
        await message.answer("⛔ Удаление доступно только Admin.")
        await state.clear()
        return

    raw = (message.text or "").strip()
    try:
        contact_id = int(raw)
    except ValueError:
        await message.answer("Введите id контакта числом, например: <code>12</code>.")
        return

    async with _sessionmaker() as session:
        contact = await get_contact_by_id(session, contact_id)
    if contact is None:
        await message.answer("Контакт не найден. Проверьте id и попробуйте ещё раз.")
        return

    await state.update_data(contact_id=contact_id)
    await message.answer(
        _contact_card(contact) + "\n<b>Удалить этот контакт?</b> (мягкое удаление)",
        reply_markup=contact_delete_confirm_menu(contact_id),
    )


@router.callback_query(F.data.startswith("contacts:delete_confirm:"))
async def delete_contact_confirm(callback: CallbackQuery, state: FSMContext, role: UserRole | None = None) -> None:
    await callback.answer()
    if not _can_delete_contacts(role):
        await callback.answer("⛔ Удаление доступно только Admin.", show_alert=True)
        return
    if callback.data is None or callback.message is None:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    try:
        contact_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный id.", show_alert=True)
        return

    try:
        async with _sessionmaker() as session:
            ok = await soft_delete_contact(session, contact_id)
    except Exception as e:
        logger.exception("Не удалось удалить контакт %s: %s", contact_id, e)
        await callback.message.answer("😔 Не удалось удалить контакт. Попробуйте ещё раз.")
        return

    await state.clear()
    if not ok:
        await callback.message.edit_text("Контакт не найден.", reply_markup=admin_contacts_menu(role))
        return
    await callback.message.edit_text("✅ Контакт удалён (мягко).", reply_markup=admin_contacts_menu(role))
