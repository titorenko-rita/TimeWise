from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class TemplateKey:
    channel: str
    style: str
    case: str
    category: str
    language: str


@dataclass(frozen=True, slots=True)
class TemplateRow:
    id: int
    channel: str
    style: str
    case: str
    category: str
    language: str
    body_text: str
    version: int
    is_active: bool
    is_deleted: bool
    created_at: datetime | None
    updated_at: datetime | None

    @property
    def key(self) -> TemplateKey:
        return TemplateKey(
            channel=self.channel,
            style=self.style,
            case=self.case,
            category=self.category,
            language=self.language,
        )


async def _maybe_audit(
    session: AsyncSession,
    *,
    actor_tg_id: int | None,
    action: str,
    entity: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Best-effort audit logging. user_id nullable in DB, so we can write without mapping.
    """
    try:
        user_id: int | None = None
        if actor_tg_id is not None:
            r = await session.execute(
                text("select id from public.users where tg_id=:tg_id limit 1"),
                {"tg_id": actor_tg_id},
            )
            user_id = r.scalar_one_or_none()

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
        # audit must never break main flow
        return


def _row_to_template(row: dict[str, Any]) -> TemplateRow:
    return TemplateRow(
        id=int(row["id"]),
        channel=str(row["channel"]),
        style=str(row["style"]),
        case=str(row["case"]),
        category=str(row["category"]),
        language=str(row["language"]),
        body_text=str(row["body_text"] or ""),
        version=int(row["version"] or 1),
        is_active=bool(row["is_active"]),
        is_deleted=bool(row.get("is_deleted") or False),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def list_latest_templates(session: AsyncSession, *, limit: int = 20, offset: int = 0) -> list[TemplateRow]:
    """
    Возвращает шаблоны по возрастанию id, без is_deleted.
    """
    r = await session.execute(
        text(
            'select id, channel, style, "case", category, language, body_text, version, '
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at "
            "from public.templates "
            "where coalesce(is_deleted,false) = false "
            "order by id asc "
            "limit :limit offset :offset"
        ),
        {"limit": limit, "offset": offset},
    )
    return [_row_to_template(dict(row)) for row in r.mappings().all()]


async def count_templates(session: AsyncSession) -> int:
    r = await session.execute(
        text("select count(*) from public.templates where coalesce(is_deleted,false)=false")
    )
    return int(r.scalar_one())


async def get_template_by_id(session: AsyncSession, template_id: int) -> TemplateRow | None:
    r = await session.execute(
        text(
            'select id, channel, style, "case", category, language, body_text, version, '
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at "
            "from public.templates where id=:id limit 1"
        ),
        {"id": template_id},
    )
    row = r.mappings().first()
    return _row_to_template(dict(row)) if row else None


async def list_versions(session: AsyncSession, *, key: TemplateKey) -> list[TemplateRow]:
    r = await session.execute(
        text(
            'select id, channel, style, "case", category, language, body_text, version, '
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at "
            "from public.templates "
            "where coalesce(is_deleted,false)=false "
            "and channel=:channel and style=:style and \"case\"=:case and category=:category and language=:language "
            "order by version desc, id desc"
        ),
        {
            "channel": key.channel,
            "style": key.style,
            "case": key.case,
            "category": key.category,
            "language": key.language,
        },
    )
    return [_row_to_template(dict(row)) for row in r.mappings().all()]


async def update_body_text(
    session: AsyncSession,
    *,
    template_id: int,
    new_body_text: str,
    actor_tg_id: int | None = None,
) -> TemplateRow | None:
    r = await session.execute(
        text(
            "update public.templates set body_text=:body, updated_at=now() "
            "where id=:id and coalesce(is_deleted,false)=false "
            "returning id, channel, style, \"case\", category, language, body_text, version, "
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at"
        ),
        {"id": template_id, "body": new_body_text},
    )
    row = r.mappings().first()
    if not row:
        await session.rollback()
        return None

    tpl = _row_to_template(dict(row))
    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="template.update_body",
        entity="template",
        entity_id=tpl.id,
        payload={"version": tpl.version},
    )
    await session.commit()
    return tpl


async def toggle_active(
    session: AsyncSession,
    *,
    template_id: int,
    is_active: bool,
    actor_tg_id: int | None = None,
) -> TemplateRow | None:
    r = await session.execute(
        text(
            "update public.templates set is_active=:active, updated_at=now() "
            "where id=:id and coalesce(is_deleted,false)=false "
            "returning id, channel, style, \"case\", category, language, body_text, version, "
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at"
        ),
        {"id": template_id, "active": is_active},
    )
    row = r.mappings().first()
    if not row:
        await session.rollback()
        return None

    tpl = _row_to_template(dict(row))
    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="template.set_active",
        entity="template",
        entity_id=tpl.id,
        payload={"is_active": tpl.is_active, "version": tpl.version},
    )
    await session.commit()
    return tpl


async def soft_delete(
    session: AsyncSession,
    *,
    template_id: int,
    actor_tg_id: int | None = None,
) -> bool:
    r = await session.execute(
        text(
            "update public.templates set is_deleted=true, is_active=false, updated_at=now() "
            "where id=:id and coalesce(is_deleted,false)=false"
        ),
        {"id": template_id},
    )
    if r.rowcount == 0:
        await session.rollback()
        return False

    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="template.delete",
        entity="template",
        entity_id=template_id,
    )
    await session.commit()
    return True


async def create_new_version(
    session: AsyncSession,
    *,
    base_template_id: int,
    actor_tg_id: int | None = None,
    activate_new: bool = False,
) -> TemplateRow | None:
    base = await get_template_by_id(session, base_template_id)
    if base is None or base.is_deleted:
        return None

    # next version within same key (ignoring deleted=false only)
    r = await session.execute(
        text(
            'select coalesce(max(version), 0) as v from public.templates '
            "where coalesce(is_deleted,false)=false "
            'and channel=:channel and style=:style and "case"=:case and category=:category and language=:language'
        ),
        {
            "channel": base.channel,
            "style": base.style,
            "case": base.case,
            "category": base.category,
            "language": base.language,
        },
    )
    next_version = int(r.scalar_one() or 0) + 1

    r = await session.execute(
        text(
            'insert into public.templates (channel, style, "case", category, language, body_text, version, is_active, created_at, updated_at, is_deleted) '
            "values (:channel, :style, :case, :category, :language, :body_text, :version, :is_active, now(), now(), false) "
            'returning id, channel, style, "case", category, language, body_text, version, '
            "coalesce(is_active,false) as is_active, coalesce(is_deleted,false) as is_deleted, created_at, updated_at"
        ),
        {
            "channel": base.channel,
            "style": base.style,
            "case": base.case,
            "category": base.category,
            "language": base.language,
            "body_text": base.body_text,
            "version": next_version,
            "is_active": bool(activate_new),
        },
    )
    row = r.mappings().first()
    if not row:
        await session.rollback()
        return None

    tpl = _row_to_template(dict(row))
    await _maybe_audit(
        session,
        actor_tg_id=actor_tg_id,
        action="template.new_version",
        entity="template",
        entity_id=tpl.id,
        payload={"from_id": base_template_id, "version": tpl.version},
    )
    await session.commit()
    return tpl

