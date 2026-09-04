from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class JobListItem:
    job_id: int
    status: str
    retry_count: int | None
    last_retry_at: Any
    next_retry_at: Any
    last_error: str | None
    event_id: int
    event_date: Any
    channel: str
    style: str
    contact_name: str | None


@dataclass(frozen=True, slots=True)
class JobCard:
    job_id: int
    status: str
    retry_count: int | None
    last_retry_at: Any
    next_retry_at: Any
    last_error: str | None
    created_at: Any
    updated_at: Any
    event_id: int
    event_date: Any
    event_status: str
    channel: str
    style: str
    contact_id: int
    contact_name: str | None
    contact_tg_username: str | None
    contact_email: str | None
    message_id: int | None
    rendered_text: str | None
    approved_at: Any
    sent_at: Any
    last_eventlog_status: str | None
    last_eventlog_error: str | None
    last_eventlog_at: Any


async def count_jobs(session: AsyncSession, *, status: str | None = None) -> int:
    where = "coalesce(is_deleted,false)=false"
    params: dict[str, Any] = {}
    if status:
        where += " and status=:st"
        params["st"] = status
    r = await session.execute(text(f"select count(*) from public.job_queue where {where}"), params)
    return int(r.scalar_one())


async def status_counts(session: AsyncSession) -> list[dict[str, Any]]:
    r = await session.execute(
        text(
            "select status, count(*) as c "
            "from public.job_queue "
            "where coalesce(is_deleted,false)=false "
            "group by status "
            "order by c desc, status asc"
        )
    )
    return [dict(row) for row in r.mappings().all()]


async def list_jobs(
    session: AsyncSession,
    *,
    limit: int = 10,
    offset: int = 0,
    status: str | None = None,
) -> list[JobListItem]:
    where = "coalesce(jq.is_deleted,false)=false"
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        where += " and jq.status=:st"
        params["st"] = status

    r = await session.execute(
        text(
            "select jq.id as job_id, jq.status, jq.retry_count, jq.last_retry_at, jq.next_retry_at, jq.last_error, "
            "jq.event_id, e.date as event_date, e.channel, e.style, "
            "(c.last_name || ' ' || c.first_name) as contact_name "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            "left join public.contacts c on c.id = e.contact_id "
            f"where {where} "
            "order by (case when jq.status='pending' then 0 when jq.status='retry' then 1 else 2 end), "
            "jq.updated_at desc nulls last, jq.id desc "
            "limit :limit offset :offset"
        ),
        params,
    )
    out: list[JobListItem] = []
    for row in r.mappings().all():
        out.append(
            JobListItem(
                job_id=int(row["job_id"]),
                status=str(row["status"]),
                retry_count=row.get("retry_count"),
                last_retry_at=row.get("last_retry_at"),
                next_retry_at=row.get("next_retry_at"),
                last_error=row.get("last_error"),
                event_id=int(row["event_id"]),
                event_date=row.get("event_date"),
                channel=str(row["channel"]),
                style=str(row["style"]),
                contact_name=row.get("contact_name"),
            )
        )
    return out


async def get_job_card(session: AsyncSession, job_id: int) -> JobCard | None:
    r = await session.execute(
        text(
            "select "
            "jq.id as job_id, jq.status, jq.retry_count, jq.last_retry_at, jq.next_retry_at, jq.last_error, "
            "jq.created_at as job_created_at, jq.updated_at as job_updated_at, "
            "jq.event_id, e.date as event_date, e.status as event_status, e.channel, e.style, e.contact_id, "
            "(c.last_name || ' ' || c.first_name) as contact_name, c.tg_username as contact_tg_username, c.email as contact_email, "
            "m.id as message_id, m.rendered_text, m.approved_at, m.sent_at, "
            "el.status as el_status, el.error_message as el_error, el.created_at as el_created_at "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            "join public.contacts c on c.id = e.contact_id "
            "left join lateral ( "
            "  select id, rendered_text, approved_at, sent_at "
            "  from public.messages "
            "  where event_id = jq.event_id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            "left join lateral ( "
            "  select status, error_message, created_at "
            "  from public.event_log "
            "  where event_id = jq.event_id "
            "  order by created_at desc nulls last, id desc "
            "  limit 1 "
            ") el on true "
            "where coalesce(jq.is_deleted,false)=false and jq.id=:jid "
            "limit 1"
        ),
        {"jid": job_id},
    )
    row = r.mappings().first()
    if not row:
        return None
    return JobCard(
        job_id=int(row["job_id"]),
        status=str(row["status"]),
        retry_count=row.get("retry_count"),
        last_retry_at=row.get("last_retry_at"),
        next_retry_at=row.get("next_retry_at"),
        last_error=row.get("last_error"),
        created_at=row.get("job_created_at"),
        updated_at=row.get("job_updated_at"),
        event_id=int(row["event_id"]),
        event_date=row.get("event_date"),
        event_status=str(row["event_status"]),
        channel=str(row["channel"]),
        style=str(row["style"]),
        contact_id=int(row["contact_id"]),
        contact_name=row.get("contact_name"),
        contact_tg_username=row.get("contact_tg_username"),
        contact_email=row.get("contact_email"),
        message_id=row.get("message_id"),
        rendered_text=row.get("rendered_text"),
        approved_at=row.get("approved_at"),
        sent_at=row.get("sent_at"),
        last_eventlog_status=row.get("el_status"),
        last_eventlog_error=row.get("el_error"),
        last_eventlog_at=row.get("el_created_at"),
    )

