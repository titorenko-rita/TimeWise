from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TemplateBlacklist


@dataclass(frozen=True, slots=True)
class BlacklistRow:
    id: int
    phrase: str
    category: str | None
    note: str | None
    created_at: datetime | None
    updated_at: datetime | None


def normalize_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", (phrase or "").strip().lower())


async def _maybe_audit(
    session: AsyncSession,
    *,
    actor_tg_id: int | None,
    action: str,
    entity: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        user_id: int | None = None
        if actor_tg_id is not None:
            result = await session.execute(
                text("select id from public.users where tg_id=:tg_id limit 1"),
                {"tg_id": actor_tg_id},
            )
            user_id = result.scalar_one_or_none()

        await session.execute(
            text(
                "insert into public.audit_log (user_id, action, entity, entity_id, payload, ts) "
                "values (:user_id, :action, :entity, :entity_id, :payload, now())"
            ),
            {
                "user_id": user_id,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "payload": json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            },
        )
    except Exception:
        return


def _to_row(item: TemplateBlacklist) -> BlacklistRow:
    return BlacklistRow(
        id=item.id,
        phrase=item.phrase,
        category=item.category,
        note=item.note,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def count_blacklist_entries(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(TemplateBlacklist)
        .where(TemplateBlacklist.is_deleted == False)  # noqa: E712
    )
    return int(result.scalar_one() or 0)


async def list_blacklist_entries(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
) -> list[BlacklistRow]:
    result = await session.execute(
        select(TemplateBlacklist)
        .where(TemplateBlacklist.is_deleted == False)  # noqa: E712
        .order_by(TemplateBlacklist.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return [_to_row(item) for item in result.scalars().all()]


async def get_blacklist_entry(session: AsyncSession, entry_id: int) -> BlacklistRow | None:
    result = await session.execute(
        select(TemplateBlacklist).where(
            TemplateBlacklist.id == entry_id,
            TemplateBlacklist.is_deleted == False,  # noqa: E712
        )
    )
    item = result.scalar_one_or_none()
    return _to_row(item) if item is not None else None


async def create_blacklist_entry(
    session: AsyncSession,
    *,
    phrase: str,
    actor_tg_id: int | None = None,
) -> tuple[BlacklistRow | None, bool]:
    normalized = normalize_phrase(phrase)
    if not normalized:
        return None, False

    existing_result = await session.execute(
        select(TemplateBlacklist).where(TemplateBlacklist.is_deleted == False)  # noqa: E712
    )
    existing = next(
        (
            item
            for item in existing_result.scalars().all()
            if normalize_phrase(item.phrase) == normalized
        ),
        None,
    )
    if existing is not None:
        await session.rollback()
        return _to_row(existing), False

    item = TemplateBlacklist(
        phrase=phrase.strip(),
        category="manual",
        is_deleted=False,
    )
    session.add(item)
    await session.flush()
    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="blacklist.create",
        entity="template_blacklist",
        entity_id=item.id,
        payload={"phrase": item.phrase},
    )
    await session.commit()
    await session.refresh(item)
    return _to_row(item), True


async def delete_blacklist_entry(
    session: AsyncSession,
    *,
    entry_id: int,
    actor_tg_id: int | None = None,
) -> bool:
    result = await session.execute(
        select(TemplateBlacklist).where(
            TemplateBlacklist.id == entry_id,
            TemplateBlacklist.is_deleted == False,  # noqa: E712
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        await session.rollback()
        return False

    phrase = item.phrase
    await session.delete(item)
    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="blacklist.delete",
        entity="template_blacklist",
        entity_id=entry_id,
        payload={"phrase": phrase},
    )
    await session.commit()
    return True
