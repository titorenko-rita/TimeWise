from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ReportSummary:
    total_events: int
    approved_messages: int
    pending_approvals: int
    rejected_approvals: int
    sent_messages: int
    failed_jobs: int
    retried_jobs: int
    success_rate_pct: float
    error_rate_pct: float
    avg_generation_ms: int
    avg_delivery_ms: int


def _period_where(period: str) -> tuple[str, dict[str, Any]]:
    if period == "today":
        return "e.date = current_date", {}
    if period == "month":
        return "date_trunc('month', e.date) = date_trunc('month', current_date)", {}
    return "1=1", {}


async def get_report_summary(session: AsyncSession, *, period: str) -> ReportSummary:
    where, params = _period_where(period)
    r = await session.execute(
        text(
            "select "
            "count(*) as total_events, "
            "count(*) filter (where m.approved_at is not null) as approved_messages, "
            "count(*) filter (where aq.status in ('pending', 'edited')) as pending_approvals, "
            "count(*) filter (where aq.status = 'rejected') as rejected_approvals, "
            "count(*) filter (where m.sent_at is not null) as sent_messages, "
            "count(*) filter (where jq.status = 'failed') as failed_jobs, "
            "count(*) filter (where coalesce(jq.retry_count, 0) > 0 or jq.status = 'retry') as retried_jobs, "
            "coalesce(100.0 * count(*) filter (where m.sent_at is not null) / nullif(count(*), 0), 0) as success_rate_pct, "
            "coalesce(100.0 * count(*) filter (where jq.status = 'failed') / nullif(count(*), 0), 0) as error_rate_pct, "
            "coalesce(avg(extract(epoch from (m.created_at - e.created_at)) * 1000) "
            "  filter (where m.created_at is not null and e.created_at is not null), 0) as avg_generation_ms, "
            "coalesce(avg(el.duration_ms) filter (where el.duration_ms is not null), 0) as avg_delivery_ms "
            "from public.events e "
            "left join public.job_queue jq on jq.event_id = e.id and coalesce(jq.is_deleted,false)=false "
            "left join lateral ( "
            "  select status "
            "  from public.approval_queue "
            "  where event_id = e.id and coalesce(is_deleted,false)=false "
            "  order by updated_at desc nulls last, id desc "
            "  limit 1 "
            ") aq on true "
            "left join lateral ( "
            "  select created_at, approved_at, sent_at "
            "  from public.messages "
            "  where event_id = e.id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            "left join lateral ( "
            "  select duration_ms "
            "  from public.event_log "
            "  where event_id = e.id "
            "  order by sent_at desc nulls last, id desc "
            "  limit 1 "
            ") el on true "
            f"where coalesce(e.is_deleted,false)=false and {where}"
        ),
        params,
    )
    row = r.mappings().one()
    return ReportSummary(
        total_events=int(row["total_events"] or 0),
        approved_messages=int(row["approved_messages"] or 0),
        pending_approvals=int(row["pending_approvals"] or 0),
        rejected_approvals=int(row["rejected_approvals"] or 0),
        sent_messages=int(row["sent_messages"] or 0),
        failed_jobs=int(row["failed_jobs"] or 0),
        retried_jobs=int(row["retried_jobs"] or 0),
        success_rate_pct=float(row["success_rate_pct"] or 0),
        error_rate_pct=float(row["error_rate_pct"] or 0),
        avg_generation_ms=int(row["avg_generation_ms"] or 0),
        avg_delivery_ms=int(row["avg_delivery_ms"] or 0),
    )


async def get_report_registry(session: AsyncSession, *, period: str, limit: int = 500) -> list[dict[str, Any]]:
    where, params = _period_where(period)
    params["limit"] = limit
    r = await session.execute(
        text(
            "select "
            "e.id as event_id, e.date as event_date, e.status as event_status, e.channel, e.style, "
            "c.id as contact_id, c.last_name, c.first_name, c.middle_name, c.company, c.position, "
            "aq.status as approval_status, "
            "jq.status as job_status, jq.retry_count, jq.last_error, "
            "m.id as message_id, m.approved_at, m.sent_at "
            "from public.events e "
            "join public.contacts c on c.id = e.contact_id "
            "left join public.job_queue jq on jq.event_id = e.id and coalesce(jq.is_deleted,false)=false "
            "left join lateral ( "
            "  select status "
            "  from public.approval_queue "
            "  where event_id = e.id and coalesce(is_deleted,false)=false "
            "  order by updated_at desc nulls last, id desc "
            "  limit 1 "
            ") aq on true "
            "left join lateral ( "
            "  select id, approved_at, sent_at "
            "  from public.messages "
            "  where event_id = e.id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            f"where coalesce(e.is_deleted,false)=false and {where} "
            "order by e.date desc nulls last, e.id desc "
            "limit :limit"
        ),
        params,
    )
    return [dict(row) for row in r.mappings().all()]

