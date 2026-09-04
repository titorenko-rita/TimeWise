"""Операции над таблицей Users."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_

from db.models import User


async def get_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


async def upsert_user(
    session: AsyncSession,
    *,
    tg_id: int,
    role: str,
    is_active: bool = True,
) -> User:
    user = await get_by_tg_id(session, tg_id)
    if user is None:
        user = User(tg_id=tg_id, role=role, is_active=is_active)
        session.add(user)
    else:
        user.role = role
        user.is_active = is_active
    await session.commit()
    await session.refresh(user)
    return user


async def set_role(session: AsyncSession, *, tg_id: int, role: str) -> User:
    """
    Устанавливает роль. Если пользователь не существует — создаёт.
    Активность не меняем, если запись уже есть.
    """
    user = await get_by_tg_id(session, tg_id)
    if user is None:
        user = User(tg_id=tg_id, role=role, is_active=True, is_deleted=False)
        session.add(user)
    else:
        user.role = role
    await session.commit()
    await session.refresh(user)
    return user


async def set_active(session: AsyncSession, *, tg_id: int, is_active: bool) -> User | None:
    user = await get_by_tg_id(session, tg_id)
    if user is None:
        return None
    user.is_active = is_active
    await session.commit()
    await session.refresh(user)
    return user


async def soft_delete_user(session: AsyncSession, *, tg_id: int) -> bool:
    user = await get_by_tg_id(session, tg_id)
    if user is None:
        return False
    user.is_deleted = True
    user.is_active = False
    await session.commit()
    return True


async def list_users(session: AsyncSession, limit: int = 200) -> Sequence[User]:
    result = await session.execute(
        select(User)
        .where(or_(User.is_deleted == False, User.is_deleted.is_(None)))  # noqa: E712
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()

