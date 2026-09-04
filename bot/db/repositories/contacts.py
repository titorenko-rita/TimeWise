"""Операции над таблицей Contacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Contact


@dataclass(frozen=True, slots=True)
class ImportContactsResult:
    imported: int
    failed: int
    errors: list[str]


async def create_contact(session: AsyncSession, **fields) -> Contact:
    contact = Contact(**fields)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def contact_exists_by_tg_username(
    session: AsyncSession,
    tg_username: str,
    *,
    exclude_contact_id: int | None = None,
) -> bool:
    normalized = tg_username.strip().lstrip("@")
    if not normalized:
        return False

    conditions = [func.lower(Contact.tg_username) == normalized.lower()]
    if exclude_contact_id is not None:
        conditions.append(Contact.id != exclude_contact_id)

    result = await session.execute(select(Contact.id).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none() is not None


async def contact_exists_by_email(
    session: AsyncSession,
    email: str,
    *,
    exclude_contact_id: int | None = None,
) -> bool:
    normalized = email.strip()
    if not normalized:
        return False

    conditions = [func.lower(Contact.email) == normalized.lower()]
    if exclude_contact_id is not None:
        conditions.append(Contact.id != exclude_contact_id)

    result = await session.execute(select(Contact.id).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none() is not None


async def contact_exists_by_tg_chat_id(
    session: AsyncSession,
    tg_chat_id: int,
    *,
    exclude_contact_id: int | None = None,
) -> bool:
    conditions = [Contact.tg_chat_id == tg_chat_id]
    if exclude_contact_id is not None:
        conditions.append(Contact.id != exclude_contact_id)

    result = await session.execute(select(Contact.id).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none() is not None


async def get_contact_by_id(session: AsyncSession, contact_id: int) -> Contact | None:
    result = await session.execute(
        select(Contact).where(Contact.id == contact_id, Contact.is_deleted == False)  # noqa: E712
    )
    return result.scalars().first()


async def update_contact(session: AsyncSession, contact_id: int, **fields) -> Contact | None:
    contact = await get_contact_by_id(session, contact_id)
    if contact is None:
        return None
    for k, v in fields.items():
        setattr(contact, k, v)
    await session.commit()
    await session.refresh(contact)
    return contact


async def soft_delete_contact(session: AsyncSession, contact_id: int) -> bool:
    contact = await get_contact_by_id(session, contact_id)
    if contact is None:
        return False
    contact.is_deleted = True
    contact.is_active = False
    await session.commit()
    return True


async def list_contacts(
    session: AsyncSession,
    limit: int = 200,
    *,
    company: str | None = None,
    position: str | None = None,
    fio_query: str | None = None,
) -> Sequence[Contact]:
    conditions = [Contact.is_deleted == False]  # noqa: E712
    if company:
        conditions.append(Contact.company.ilike(f"%{company.strip()}%"))
    if position:
        conditions.append(Contact.position.ilike(f"%{position.strip()}%"))
    if fio_query:
        tokens = [token for token in fio_query.strip().split() if token]
        for token in tokens:
            pattern = f"%{token}%"
            conditions.append(
                or_(
                    Contact.last_name.ilike(pattern),
                    Contact.first_name.ilike(pattern),
                    Contact.middle_name.ilike(pattern),
                )
            )
    result = await session.execute(
        select(Contact)
        .where(and_(*conditions))
        .order_by(Contact.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def import_contacts(session: AsyncSession, rows: Sequence[dict]) -> ImportContactsResult:
    imported = 0
    failed = 0
    errors: list[str] = []

    for idx, fields in enumerate(rows, start=1):
        try:
            async with session.begin_nested():
                session.add(Contact(**fields))
                await session.flush()
            imported += 1
        except SQLAlchemyError as e:
            failed += 1
            errors.append(f"Строка {idx}: {e.__class__.__name__}")

    await session.commit()
    return ImportContactsResult(imported=imported, failed=failed, errors=errors[:20])

