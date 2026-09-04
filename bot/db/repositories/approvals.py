from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ApprovalListItem:
    approval_id: int
    status: str
    updated_at: Any
    event_id: int
    event_date: Any
    channel: str | None
    style: str | None
    contact_name: str | None
    responsible_id: int | None
    holiday_id: int | None


@dataclass(frozen=True, slots=True)
class ApprovalCard:
    approval_id: int
    approval_status: str
    approval_comment: str | None
    event_id: int
    event_date: Any
    event_status: str | None
    channel: str | None
    style: str | None
    contact_id: int | None
    contact_name: str | None
    contact_tg_username: str | None
    contact_email: str | None
    contact_position: str | None
    contact_company: str | None
    contact_notes: str | None
    responsible_user_id: int | None
    responsible_tg_id: int | None
    message_id: int | None
    rendered_text: str | None
    approved_by: int | None
    approved_at: Any
    sent_at: Any


async def get_actor_user_id(session: AsyncSession, actor_tg_id: int) -> int | None:
    r = await session.execute(
        text("select id from public.users where tg_id=:tg_id and coalesce(is_deleted,false)=false limit 1"),
        {"tg_id": actor_tg_id},
    )
    v = r.scalar_one_or_none()
    return int(v) if v is not None else None


async def _audit(
    session: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
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


async def list_approvals(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    is_admin: bool,
    event_kind: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[ApprovalListItem]:
    where = (
        "coalesce(aq.is_deleted,false)=false "
        "and aq.id in ("
        "select max(aq2.id) "
        "from public.approval_queue aq2 "
        "where coalesce(aq2.is_deleted,false)=false "
        "group by aq2.event_id)"
    )
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if not is_admin:
        where += " and aq.responsible_id = :rid"
        params["rid"] = actor_user_id or -1
    if event_kind == "birthday":
        where += " and e.holiday_id is null"
    elif event_kind == "holiday":
        where += " and e.holiday_id is not null"

    r = await session.execute(
        text(
            "select aq.id as approval_id, aq.status, aq.updated_at, aq.event_id, aq.responsible_id, e.holiday_id, "
            "e.date as event_date, e.channel, e.style, "
            "(c.last_name || ' ' || c.first_name) as contact_name "
            "from public.approval_queue aq "
            "join public.events e on e.id = aq.event_id "
            "left join public.contacts c on c.id = e.contact_id "
            f"where {where} "
            "order by (case when aq.status='pending' then 0 else 1 end), aq.updated_at desc nulls last, aq.id desc "
            "limit :limit offset :offset"
        ),
        params,
    )
    out: list[ApprovalListItem] = []
    for row in r.mappings().all():
        out.append(
            ApprovalListItem(
                approval_id=int(row["approval_id"]),
                status=str(row["status"]),
                updated_at=row.get("updated_at"),
                event_id=int(row["event_id"]),
                event_date=row.get("event_date"),
                channel=row.get("channel"),
                style=row.get("style"),
                contact_name=row.get("contact_name"),
                responsible_id=row.get("responsible_id"),
                holiday_id=row.get("holiday_id"),
            )
        )
    return out


async def count_today_pending_approval_breakdown(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    is_admin: bool,
) -> tuple[int, int]:
    where = (
        "coalesce(aq.is_deleted,false)=false "
        "and aq.id in ("
        "select max(aq2.id) "
        "from public.approval_queue aq2 "
        "where coalesce(aq2.is_deleted,false)=false "
        "group by aq2.event_id) "
        "and e.date = current_date "
        "and coalesce(e.status, '') <> 'sent' "
        "and aq.status in ('pending', 'edited')"
    )
    params: dict[str, Any] = {}
    if not is_admin:
        where += " and aq.responsible_id = :rid"
        params["rid"] = actor_user_id or -1

    r = await session.execute(
        text(
            "select "
            "count(*) filter (where e.holiday_id is null) as birthday_count, "
            "count(*) filter (where e.holiday_id is not null) as holiday_count "
            "from public.approval_queue aq "
            "join public.events e on e.id = aq.event_id "
            f"where {where}"
        ),
        params,
    )
    row = r.mappings().first()
    if not row:
        return 0, 0
    return int(row.get("birthday_count") or 0), int(row.get("holiday_count") or 0)


async def count_today_pending_approvals(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    is_admin: bool,
) -> int:
    birthday_count, holiday_count = await count_today_pending_approval_breakdown(
        session,
        actor_user_id=actor_user_id,
        is_admin=is_admin,
    )
    return birthday_count + holiday_count


async def list_today_pending_approval_ids(
    session: AsyncSession,
    *,
    actor_user_id: int | None,
    is_admin: bool,
    event_kind: str | None = None,
) -> list[int]:
    where = (
        "coalesce(aq.is_deleted,false)=false "
        "and aq.id in ("
        "select max(aq2.id) "
        "from public.approval_queue aq2 "
        "where coalesce(aq2.is_deleted,false)=false "
        "group by aq2.event_id) "
        "and e.date = current_date "
        "and coalesce(e.status, '') <> 'sent' "
        "and aq.status in ('pending', 'edited')"
    )
    params: dict[str, Any] = {}
    if not is_admin:
        where += " and aq.responsible_id = :rid"
        params["rid"] = actor_user_id or -1
    if event_kind == "birthday":
        where += " and e.holiday_id is null"
    elif event_kind == "holiday":
        where += " and e.holiday_id is not null"

    r = await session.execute(
        text(
            "select aq.id "
            "from public.approval_queue aq "
            "join public.events e on e.id = aq.event_id "
            f"where {where} "
            "order by aq.updated_at desc nulls last, aq.id desc"
        ),
        params,
    )
    return [int(value) for value in r.scalars().all()]


async def count_approvals(
    session: AsyncSession, *, actor_user_id: int | None, is_admin: bool
) -> int:
    where = (
        "coalesce(is_deleted,false)=false "
        "and id in ("
        "select max(aq2.id) "
        "from public.approval_queue aq2 "
        "where coalesce(aq2.is_deleted,false)=false "
        "group by aq2.event_id)"
    )
    params: dict[str, Any] = {}
    if not is_admin:
        where += " and responsible_id = :rid"
        params["rid"] = actor_user_id or -1
    r = await session.execute(text(f"select count(*) from public.approval_queue where {where}"), params)
    return int(r.scalar_one())


async def get_approval_card(
    session: AsyncSession,
    *,
    approval_id: int,
    actor_user_id: int | None,
    is_admin: bool,
) -> ApprovalCard | None:
    # LATERAL join to pick latest message for event
    where = "coalesce(aq.is_deleted,false)=false and aq.id=:aid"
    params: dict[str, Any] = {"aid": approval_id}
    if not is_admin:
        where += " and aq.responsible_id = :rid"
        params["rid"] = actor_user_id or -1

    r = await session.execute(
        text(
            "select "
            "aq.id as approval_id, aq.status as approval_status, aq.comment as approval_comment, "
            "aq.event_id, aq.responsible_id as responsible_user_id, "
            "e.date as event_date, e.status as event_status, e.channel, e.style, e.contact_id, "
            "(c.last_name || ' ' || c.first_name) as contact_name, "
            "c.tg_username as contact_tg_username, c.email as contact_email, "
            "c.position as contact_position, c.company as contact_company, c.notes as contact_notes, "
            "u.tg_id as responsible_tg_id, "
            "m.id as message_id, m.rendered_text, m.approved_by, m.approved_at, m.sent_at "
            "from public.approval_queue aq "
            "join public.events e on e.id = aq.event_id "
            "left join public.contacts c on c.id = e.contact_id "
            "left join public.users u on u.id = aq.responsible_id "
            "left join lateral ( "
            "  select id, rendered_text, approved_by, approved_at, sent_at "
            "  from public.messages "
            "  where event_id = aq.event_id and coalesce(is_deleted,false)=false "
            "  order by id desc "
            "  limit 1 "
            ") m on true "
            f"where {where} "
            "limit 1"
        ),
        params,
    )
    row = r.mappings().first()
    if not row:
        return None
    return ApprovalCard(
        approval_id=int(row["approval_id"]),
        approval_status=str(row["approval_status"]),
        approval_comment=row.get("approval_comment"),
        event_id=int(row["event_id"]),
        event_date=row.get("event_date"),
        event_status=row.get("event_status"),
        channel=row.get("channel"),
        style=row.get("style"),
        contact_id=row.get("contact_id"),
        contact_name=row.get("contact_name"),
        contact_tg_username=row.get("contact_tg_username"),
        contact_email=row.get("contact_email"),
        contact_position=row.get("contact_position"),
        contact_company=row.get("contact_company"),
        contact_notes=row.get("contact_notes"),
        responsible_user_id=row.get("responsible_user_id"),
        responsible_tg_id=row.get("responsible_tg_id"),
        message_id=row.get("message_id"),
        rendered_text=row.get("rendered_text"),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        sent_at=row.get("sent_at"),
    )


async def approve(
    session: AsyncSession,
    *,
    approval_id: int,
    actor_user_id: int,
    is_admin: bool,
) -> tuple[bool, str]:
    card = await get_approval_card(
        session, approval_id=approval_id, actor_user_id=actor_user_id, is_admin=is_admin
    )
    if card is None:
        return False, "Заявка не найдена или недоступна."
    if card.approval_status not in {"pending", "edited"}:
        return False, f"Нельзя одобрить заявку со статусом {card.approval_status!r}."
    if card.message_id is None:
        return False, "У заявки нет сообщения для согласования (messages не найдено)."

    if card.sent_at is not None or card.event_status == "sent":
        await session.execute(
            text("update public.approval_queue set status='approved', updated_at=now() where id=:id"),
            {"id": approval_id},
        )
        await _audit(
            session,
            user_id=actor_user_id,
            action="approval.approve_already_sent",
            entity="approval_queue",
            entity_id=approval_id,
            payload={"event_id": card.event_id, "message_id": card.message_id},
        )
        await session.commit()
        return True, "ℹ️ Сообщение по этой заявке уже было отправлено ранее. Повторная отправка не выполнялась."

    await session.execute(
        text("update public.approval_queue set status='approved', updated_at=now() where id=:id"),
        {"id": approval_id},
    )
    await session.execute(
        text(
            "update public.messages set approved_by=:uid, approved_at=now(), updated_at=now() where id=:mid"
        ),
        {"uid": actor_user_id, "mid": card.message_id},
    )

    # Reuse a single queue row per event_id: if the job already exists, return it to pending.
    jr = await session.execute(
        text(
            "insert into public.job_queue (event_id, status, retry_count, last_retry_at, next_retry_at, last_error, created_at, updated_at, is_deleted) "
            "values (:eid, 'pending', 0, null, null, null, now(), now(), false) "
            "on conflict (event_id) do update set "
            "status='pending', "
            "retry_count=0, "
            "last_retry_at=null, "
            "next_retry_at=null, "
            "last_error=null, "
            "updated_at=now(), "
            "is_deleted=false"
        ),
        {"eid": card.event_id},
    )

    await _audit(
        session,
        user_id=actor_user_id,
        action="approval.approve",
        entity="approval_queue",
        entity_id=approval_id,
        payload={
            "event_id": card.event_id,
            "message_id": card.message_id,
            "job_upserted": bool(jr.rowcount and jr.rowcount > 0),
        },
    )
    await session.commit()
    return True, "✅ Заявка одобрена. Задача отправки поставлена в JobQueue."


async def reject(
    session: AsyncSession,
    *,
    approval_id: int,
    actor_user_id: int,
    is_admin: bool,
) -> tuple[bool, str]:
    card = await get_approval_card(
        session, approval_id=approval_id, actor_user_id=actor_user_id, is_admin=is_admin
    )
    if card is None:
        return False, "Заявка не найдена или недоступна."
    if card.approval_status not in {"pending", "edited"}:
        return False, f"Нельзя отменить заявку со статусом {card.approval_status!r}."

    await session.execute(
        text("update public.approval_queue set status='rejected', updated_at=now() where id=:id"),
        {"id": approval_id},
    )
    await _audit(
        session,
        user_id=actor_user_id,
        action="approval.reject",
        entity="approval_queue",
        entity_id=approval_id,
        payload={"event_id": card.event_id, "message_id": card.message_id},
    )
    await session.commit()
    return True, "✅ Заявка отменена (rejected)."


async def edit_rendered_text(
    session: AsyncSession,
    *,
    approval_id: int,
    actor_user_id: int,
    is_admin: bool,
    new_text: str,
) -> tuple[bool, str]:
    card = await get_approval_card(
        session, approval_id=approval_id, actor_user_id=actor_user_id, is_admin=is_admin
    )
    if card is None:
        return False, "Заявка не найдена или недоступна."
    if card.approval_status not in {"pending", "edited"}:
        return False, f"Нельзя править заявку со статусом {card.approval_status!r}."
    if card.message_id is None:
        return False, "У заявки нет сообщения (messages не найдено)."

    old = card.rendered_text or ""
    await session.execute(
        text(
            "update public.messages set rendered_text=:t, approved_by=null, approved_at=null, updated_at=now() "
            "where id=:mid"
        ),
        {"t": new_text, "mid": card.message_id},
    )
    await session.execute(
        text("update public.approval_queue set status='edited', updated_at=now() where id=:id"),
        {"id": approval_id},
    )
    await _audit(
        session,
        user_id=actor_user_id,
        action="approval.edit_text",
        entity="approval_queue",
        entity_id=approval_id,
        payload={
            "event_id": card.event_id,
            "message_id": card.message_id,
            "old_text": old[:5000],
            "new_text": new_text[:5000],
        },
    )
    await session.commit()
    return True, "✅ Текст обновлён. Заявка возвращена в согласование (edited)."


async def bulk_approve_today(
    session: AsyncSession,
    *,
    actor_user_id: int,
    is_admin: bool,
    event_kind: str | None = None,
) -> tuple[int, int, list[str]]:
    approval_ids = await list_today_pending_approval_ids(
        session,
        actor_user_id=actor_user_id,
        is_admin=is_admin,
        event_kind=event_kind,
    )
    approved = 0
    skipped = 0
    errors: list[str] = []
    for approval_id in approval_ids:
        ok, msg = await approve(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=is_admin,
        )
        if ok:
            approved += 1
        else:
            skipped += 1
            if len(errors) < 10:
                errors.append(f"id {approval_id}: {msg}")
    return approved, skipped, errors


async def bulk_reject_today(
    session: AsyncSession,
    *,
    actor_user_id: int,
    is_admin: bool,
    event_kind: str | None = None,
) -> tuple[int, int, list[str]]:
    approval_ids = await list_today_pending_approval_ids(
        session,
        actor_user_id=actor_user_id,
        is_admin=is_admin,
        event_kind=event_kind,
    )
    rejected = 0
    skipped = 0
    errors: list[str] = []
    for approval_id in approval_ids:
        ok, msg = await reject(
            session,
            approval_id=approval_id,
            actor_user_id=actor_user_id,
            is_admin=is_admin,
        )
        if ok:
            rejected += 1
        else:
            skipped += 1
            if len(errors) < 10:
                errors.append(f"id {approval_id}: {msg}")
    return rejected, skipped, errors


async def expire_stale_approvals(
    session: AsyncSession,
    *,
    timeout_hours: int,
) -> tuple[int, list[str]]:
    rows = await session.execute(
        text(
            "select aq.id as approval_id, aq.event_id, aq.updated_at, aq.created_at "
            "from public.approval_queue aq "
            "where coalesce(aq.is_deleted,false)=false "
            "and aq.status in ('pending', 'edited') "
            "and coalesce(aq.updated_at, aq.created_at) <= (now() - make_interval(hours => :timeout_hours)) "
            "order by aq.id asc"
        ),
        {"timeout_hours": timeout_hours},
    )
    expired = 0
    errors: list[str] = []

    for row in rows.mappings().all():
        approval_id = int(row["approval_id"])
        event_id = int(row["event_id"])
        try:
            await session.execute(
                text(
                    "update public.approval_queue "
                    "set status='rejected', "
                    "comment=trim(both from concat(coalesce(comment, ''), "
                    "case when coalesce(comment, '') <> '' then E'\\n' else '' end, "
                    ":comment_suffix)), "
                    "updated_at=now() "
                    "where id=:approval_id"
                ),
                {
                    "approval_id": approval_id,
                    "comment_suffix": f"Автоотмена по таймауту {timeout_hours} ч.",
                },
            )
            await session.execute(
                text(
                    "update public.events "
                    "set status='failed', updated_at=now() "
                    "where id=:event_id and coalesce(is_deleted,false)=false"
                ),
                {"event_id": event_id},
            )
            await session.execute(
                text(
                    "update public.job_queue "
                    "set status='failed', "
                    "last_error=:last_error, "
                    "updated_at=now() "
                    "where event_id=:event_id "
                    "and coalesce(is_deleted,false)=false "
                    "and status in ('pending', 'retry')"
                ),
                {
                    "event_id": event_id,
                    "last_error": f"Approval timed out after {timeout_hours} hour(s).",
                },
            )
            await _audit(
                session,
                user_id=None,
                action="approval.timeout_reject",
                entity="approval_queue",
                entity_id=approval_id,
                payload={"event_id": event_id, "timeout_hours": timeout_hours},
            )
            expired += 1
        except Exception as exc:
            if len(errors) < 10:
                errors.append(f"id {approval_id}: {exc}")

    return expired, errors


async def expire_stale_approvals(
    session: AsyncSession,
    *,
    timeout_hours: int,
) -> tuple[int, list[str]]:
    rows = await session.execute(
        text(
            "select aq.id as approval_id, aq.event_id, aq.updated_at, aq.created_at "
            "from public.approval_queue aq "
            "where coalesce(aq.is_deleted,false)=false "
            "and aq.status in ('pending', 'edited') "
            "and coalesce(aq.updated_at, aq.created_at) <= (now() - make_interval(hours => :timeout_hours)) "
            "order by aq.id asc"
        ),
        {"timeout_hours": timeout_hours},
    )
    expired = 0
    errors: list[str] = []

    for row in rows.mappings().all():
        approval_id = int(row["approval_id"])
        event_id = int(row["event_id"])
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "update public.approval_queue "
                        "set status='rejected', "
                        "comment=trim(both from concat(coalesce(comment, ''), "
                        "case when coalesce(comment, '') <> '' then E'\\n' else '' end, "
                        "cast(:comment_suffix as text))), "
                        "updated_at=now() "
                        "where id=:approval_id"
                    ),
                    {
                        "approval_id": approval_id,
                        "comment_suffix": f"Автоотмена по таймауту {timeout_hours} ч.",
                    },
                )
                await session.execute(
                    text(
                        "update public.events "
                        "set status='failed', updated_at=now() "
                        "where id=:event_id and coalesce(is_deleted,false)=false"
                    ),
                    {"event_id": event_id},
                )
                await session.execute(
                    text(
                        "update public.job_queue "
                        "set status='failed', "
                        "last_error=:last_error, "
                        "updated_at=now() "
                        "where event_id=:event_id "
                        "and coalesce(is_deleted,false)=false "
                        "and status in ('pending', 'retry')"
                    ),
                    {
                        "event_id": event_id,
                        "last_error": f"Approval timed out after {timeout_hours} hour(s).",
                    },
                )
                await _audit(
                    session,
                    user_id=None,
                    action="approval.timeout_reject",
                    entity="approval_queue",
                    entity_id=approval_id,
                    payload={"event_id": event_id, "timeout_hours": timeout_hours},
                )
            expired += 1
        except Exception as exc:
            if len(errors) < 10:
                errors.append(f"id {approval_id}: {exc}")

    return expired, errors
