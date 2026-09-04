from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class MonitoringSummary:
    sent: int
    pending: int
    retry: int
    failed: int
    partial: int


@dataclass(frozen=True, slots=True)
class MonitoringListItem:
    job_id: int
    job_status: str
    retry_count: int | None
    last_retry_at: Any
    next_retry_at: Any
    last_error: str | None
    event_id: int
    event_date: Any
    channel: str
    style: str
    contact_name: str | None
    approved_at: Any
    sent_at: Any
    approval_status: str | None


@dataclass(frozen=True, slots=True)
class MonitoringDetail:
    job_id: int
    job_status: str
    retry_count: int | None
    last_retry_at: Any
    next_retry_at: Any
    last_error: str | None
    job_created_at: Any
    job_updated_at: Any
    event_id: int
    event_date: Any
    event_status: str
    channel: str
    style: str
    responsible_id: int | None
    responsible_tg_id: int | None
    contact_id: int
    contact_name: str | None
    contact_tg_username: str | None
    contact_email: str | None
    message_id: int | None
    rendered_text: str | None
    approved_by: int | None
    approved_at: Any
    sent_at: Any
    approval_id: int | None
    approval_status: str | None
    last_eventlog_status: str | None
    last_eventlog_error: str | None
    last_eventlog_at: Any


async def get_actor_user_id(session: AsyncSession, actor_tg_id: int) -> int | None:
    r = await session.execute(
        text("select id from public.users where tg_id=:tg and coalesce(is_deleted,false)=false limit 1"),
        {"tg": actor_tg_id},
    )
    v = r.scalar_one_or_none()
    return int(v) if v is not None else None


async def summary(session: AsyncSession, *, responsible_user_id: int | None = None) -> MonitoringSummary:
    where = "coalesce(jq.is_deleted,false)=false"
    params: dict[str, Any] = {}
    if responsible_user_id is not None:
        where += " and e.responsible_id = :rid"
        params["rid"] = responsible_user_id

    r = await session.execute(
        text(
            "select jq.status, count(*) as c "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            f"where {where} "
            "group by jq.status"
        ),
        params,
    )
    counts = {row["status"]: int(row["c"]) for row in r.mappings().all()}
    return MonitoringSummary(
        sent=counts.get("sent", 0),
        pending=counts.get("pending", 0),
        retry=counts.get("retry", 0),
        failed=counts.get("failed", 0),
        partial=counts.get("partial", 0),
    )


async def count_items(
    session: AsyncSession,
    *,
    responsible_user_id: int | None,
    status: str | None,
    date_from: Any | None,
    date_to: Any | None,
) -> int:
    where = "coalesce(jq.is_deleted,false)=false"
    params: dict[str, Any] = {}
    if responsible_user_id is not None:
        where += " and e.responsible_id = :rid"
        params["rid"] = responsible_user_id
    if status is not None:
        where += " and jq.status = :st"
        params["st"] = status
    if date_from is not None:
        where += " and e.date >= :df"
        params["df"] = date_from
    if date_to is not None:
        where += " and e.date <= :dt"
        params["dt"] = date_to

    r = await session.execute(
        text(
            "select count(*) "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            f"where {where}"
        ),
        params,
    )
    return int(r.scalar_one())


async def list_items(
    session: AsyncSession,
    *,
    responsible_user_id: int | None,
    status: str | None,
    date_from: Any | None,
    date_to: Any | None,
    limit: int,
    offset: int,
) -> list[MonitoringListItem]:
    where = "coalesce(jq.is_deleted,false)=false"
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if responsible_user_id is not None:
        where += " and e.responsible_id = :rid"
        params["rid"] = responsible_user_id
    if status is not None:
        where += " and jq.status = :st"
        params["st"] = status
    if date_from is not None:
        where += " and e.date >= :df"
        params["df"] = date_from
    if date_to is not None:
        where += " and e.date <= :dt"
        params["dt"] = date_to

    r = await session.execute(
        text(
            "select "
            "jq.id as job_id, jq.status as job_status, jq.retry_count, jq.last_retry_at, jq.next_retry_at, jq.last_error, "
            "e.id as event_id, e.date as event_date, e.channel, e.style, "
            "(c.last_name || ' ' || c.first_name) as contact_name, "
            "m.approved_at, m.sent_at, "
            "aq.status as approval_status "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            "join public.contacts c on c.id = e.contact_id "
            "left join lateral ( "
            "  select approved_at, sent_at "
            "  from public.messages "
            "  where event_id = jq.event_id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            "left join lateral ( "
            "  select status "
            "  from public.approval_queue "
            "  where event_id = jq.event_id and coalesce(is_deleted,false)=false "
            "  order by updated_at desc nulls last, id desc "
            "  limit 1 "
            ") aq on true "
            f"where {where} "
            "order by "
            "(case jq.status when 'failed' then 0 when 'retry' then 1 when 'partial' then 2 when 'pending' then 3 when 'sent' then 4 else 5 end), "
            "jq.updated_at desc nulls last, jq.id desc "
            "limit :limit offset :offset"
        ),
        params,
    )
    out: list[MonitoringListItem] = []
    for row in r.mappings().all():
        out.append(
            MonitoringListItem(
                job_id=int(row["job_id"]),
                job_status=str(row["job_status"]),
                retry_count=row.get("retry_count"),
                last_retry_at=row.get("last_retry_at"),
                next_retry_at=row.get("next_retry_at"),
                last_error=row.get("last_error"),
                event_id=int(row["event_id"]),
                event_date=row.get("event_date"),
                channel=str(row["channel"]),
                style=str(row["style"]),
                contact_name=row.get("contact_name"),
                approved_at=row.get("approved_at"),
                sent_at=row.get("sent_at"),
                approval_status=row.get("approval_status"),
            )
        )
    return out


async def get_detail(
    session: AsyncSession,
    *,
    job_id: int,
    responsible_user_id: int | None,
) -> MonitoringDetail | None:
    where = "coalesce(jq.is_deleted,false)=false and jq.id=:jid"
    params: dict[str, Any] = {"jid": job_id}
    if responsible_user_id is not None:
        where += " and e.responsible_id = :rid"
        params["rid"] = responsible_user_id

    r = await session.execute(
        text(
            "select "
            "jq.id as job_id, jq.status as job_status, jq.retry_count, jq.last_retry_at, jq.next_retry_at, jq.last_error, "
            "jq.created_at as job_created_at, jq.updated_at as job_updated_at, "
            "e.id as event_id, e.date as event_date, e.status as event_status, e.channel, e.style, e.responsible_id, "
            "u.tg_id as responsible_tg_id, "
            "c.id as contact_id, (c.last_name || ' ' || c.first_name) as contact_name, c.tg_username as contact_tg_username, c.email as contact_email, "
            "m.id as message_id, m.rendered_text, m.approved_by, m.approved_at, m.sent_at, "
            "aq.id as approval_id, aq.status as approval_status, "
            "el.status as el_status, el.error_message as el_error, el.created_at as el_created_at "
            "from public.job_queue jq "
            "join public.events e on e.id = jq.event_id "
            "join public.contacts c on c.id = e.contact_id "
            "left join public.users u on u.id = e.responsible_id "
            "left join lateral ( "
            "  select id, rendered_text, approved_by, approved_at, sent_at "
            "  from public.messages "
            "  where event_id = jq.event_id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            "left join lateral ( "
            "  select id, status "
            "  from public.approval_queue "
            "  where event_id = jq.event_id and coalesce(is_deleted,false)=false "
            "  order by updated_at desc nulls last, id desc "
            "  limit 1 "
            ") aq on true "
            "left join lateral ( "
            "  select status, error_message, created_at "
            "  from public.event_log "
            "  where event_id = jq.event_id "
            "  order by created_at desc nulls last, id desc "
            "  limit 1 "
            ") el on true "
            f"where {where} "
            "limit 1"
        ),
        params,
    )
    row = r.mappings().first()
    if not row:
        return None
    return MonitoringDetail(
        job_id=int(row["job_id"]),
        job_status=str(row["job_status"]),
        retry_count=row.get("retry_count"),
        last_retry_at=row.get("last_retry_at"),
        next_retry_at=row.get("next_retry_at"),
        last_error=row.get("last_error"),
        job_created_at=row.get("job_created_at"),
        job_updated_at=row.get("job_updated_at"),
        event_id=int(row["event_id"]),
        event_date=row.get("event_date"),
        event_status=str(row["event_status"]),
        channel=str(row["channel"]),
        style=str(row["style"]),
        responsible_id=row.get("responsible_id"),
        responsible_tg_id=row.get("responsible_tg_id"),
        contact_id=int(row["contact_id"]),
        contact_name=row.get("contact_name"),
        contact_tg_username=row.get("contact_tg_username"),
        contact_email=row.get("contact_email"),
        message_id=row.get("message_id"),
        rendered_text=row.get("rendered_text"),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        sent_at=row.get("sent_at"),
        approval_id=row.get("approval_id"),
        approval_status=row.get("approval_status"),
        last_eventlog_status=row.get("el_status"),
        last_eventlog_error=row.get("el_error"),
        last_eventlog_at=row.get("el_created_at"),
    )


async def retry_now(
    session: AsyncSession,
    *,
    job_id: int,
    responsible_user_id: int | None,
    actor_user_id: int | None,
) -> tuple[bool, str]:
    detail = await get_detail(session, job_id=job_id, responsible_user_id=responsible_user_id)
    if detail is None:
        return False, "Задача не найдена."
    if detail.job_status == "sent":
        return False, "Задача уже отправлена (sent)."

    r = await session.execute(
        text(
            "update public.job_queue "
            "set status='pending', next_retry_at=now(), updated_at=now() "
            "where id=:jid and coalesce(is_deleted,false)=false"
        ),
        {"jid": job_id},
    )
    if r.rowcount == 0:
        await session.rollback()
        return False, "Не удалось обновить задачу."

    # audit best-effort (same shape as other audit writes)
    try:
        await session.execute(
            text(
                "insert into public.audit_log (user_id, action, entity, entity_id, payload, ts) "
                "values (:uid, :action, :entity, :eid, :payload, now())"
            ),
            {
                "uid": actor_user_id,
                "action": "job_queue.retry_now",
                "entity": "job_queue",
                "eid": job_id,
                "payload": json.dumps({"event_id": detail.event_id, "prev_status": detail.job_status}, ensure_ascii=False),
            },
        )
    except Exception:
        pass

    await session.commit()
    return True, "✅ Поставлено в «в ожидании» (pending) и будет обработано воркером."

