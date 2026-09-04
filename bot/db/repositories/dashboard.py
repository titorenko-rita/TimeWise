from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TableCount:
    table: str
    total: int


async def get_table_counts(session: AsyncSession, tables: Iterable[str]) -> list[TableCount]:
    result: list[TableCount] = []
    for t in tables:
        r = await session.execute(text(f"select count(*) as c from public.{t}"))
        c = int(r.scalar_one())
        result.append(TableCount(table=t, total=c))
    return result


async def get_status_counts(
    session: AsyncSession, *, table: str, status_column: str = "status", where: str | None = None
) -> list[dict[str, Any]]:
    sql = f"select {status_column} as status, count(*) as c from public.{table}"
    if where:
        sql += f" where {where}"
    sql += f" group by {status_column} order by c desc, {status_column} asc"
    r = await session.execute(text(sql))
    return [dict(row) for row in r.mappings().all()]


async def list_templates(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select id, channel, style, category, language, version, is_active, updated_at "
            "from public.templates "
            "where coalesce(is_deleted, false) = false "
            "order by updated_at desc nulls last, id desc "
            "limit :limit"
        ),
        {"limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]


async def list_events(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select e.id, e.date, e.status, e.channel, e.style, e.responsible_id, "
            "c.last_name, c.first_name "
            "from public.events e "
            "left join public.contacts c on c.id = e.contact_id "
            "where coalesce(e.is_deleted, false) = false "
            "order by e.date desc nulls last, e.id desc "
            "limit :limit"
        ),
        {"limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]


async def list_messages(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select id, event_id, template_id, approved_by, approved_at, sent_at, updated_at "
            "from public.messages "
            "where coalesce(is_deleted, false) = false "
            "order by updated_at desc nulls last, id desc "
            "limit :limit"
        ),
        {"limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]


async def list_job_queue(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select id, event_id, status, retry_count, last_retry_at, updated_at "
            "from public.job_queue "
            "where coalesce(is_deleted, false) = false "
            "order by updated_at desc nulls last, id desc "
            "limit :limit"
        ),
        {"limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]


async def list_approval_queue(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select id, event_id, responsible_id, status, comment, updated_at "
            "from public.approval_queue "
            "where coalesce(is_deleted, false) = false "
            "order by updated_at desc nulls last, id desc "
            "limit :limit"
        ),
        {"limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]


async def list_user_events_by_tg_id(session: AsyncSession, tg_id: int, limit: int = 10) -> list[dict[str, Any]]:
    # mapping: events.responsible_id -> users.id, users.tg_id -> telegram user id
    r = await session.execute(
        text(
            "select e.id, e.date, e.status, e.channel, e.style, "
            "c.last_name, c.first_name "
            "from public.events e "
            "join public.users u on u.id = e.responsible_id "
            "left join public.contacts c on c.id = e.contact_id "
            "where coalesce(e.is_deleted, false) = false and u.tg_id = :tg_id "
            "order by e.date asc nulls last, e.id desc "
            "limit :limit"
        ),
        {"tg_id": tg_id, "limit": limit},
    )
    return [dict(row) for row in r.mappings().all()]

