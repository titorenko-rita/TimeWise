from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ApprovalActionResult:
    approval_id: int
    event_id: int
    job_id: int | None
    acted_by: int
    status: str


async def _get_current_user(session: AsyncSession, tg_id: int) -> tuple[int, str] | None:
    query = text(
        """
        SELECT id, role
        FROM public.users
        WHERE tg_id = :tg_id
          AND (is_deleted = false OR is_deleted IS NULL)
          AND (is_active = true OR is_active IS NULL)
        LIMIT 1;
        """
    )
    result = await session.execute(query, {"tg_id": tg_id})
    row = result.first()
    if not row:
        return None
    return int(row[0]), str(row[1])


async def approve_message(
    session: AsyncSession,
    approval_id: int,
    current_tg_id: int,
) -> ApprovalActionResult:
    """
    Подтверждает заявку на согласование и ставит событие в job_queue.
    """
    current_user = await _get_current_user(session, current_tg_id)
    if not current_user:
        raise PermissionError("Пользователь не найден или отключен")

    current_user_id, role = current_user

    if role not in ("Admin", "Editor"):
        raise PermissionError("Подтверждение доступно только ролям Admin и Editor")

    approval_query = text(
        """
        SELECT aq.id, aq.event_id, aq.responsible_id, aq.status, m.id AS message_id
        FROM public.approval_queue aq
        JOIN public.messages m ON m.event_id = aq.event_id
        WHERE aq.id = :approval_id
          AND aq.is_deleted = false
          AND m.is_deleted = false
        FOR UPDATE;
        """
    )
    approval_result = await session.execute(approval_query, {"approval_id": approval_id})
    approval_row = approval_result.first()
    if not approval_row:
        raise ValueError("Заявка на согласование не найдена")

    found_approval_id, event_id, responsible_id, status, _message_id = approval_row

    if status not in ("pending", "edited"):
        raise ValueError(f"Нельзя подтвердить заявку со статусом '{status}'")

    if role != "Admin" and responsible_id != current_user_id:
        raise PermissionError("Подтверждать заявку может только ответственный Editor или Admin")

    await session.execute(
        text(
            """
            UPDATE public.approval_queue
            SET status = 'approved',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :approval_id;
            """
        ),
        {"approval_id": int(found_approval_id)},
    )

    await session.execute(
        text(
            """
            UPDATE public.messages
            SET approved_by = :user_id,
                approved_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE event_id = :event_id
              AND is_deleted = false;
            """
        ),
        {"user_id": current_user_id, "event_id": int(event_id)},
    )

    job_result = await session.execute(
        text(
            """
            INSERT INTO public.job_queue (
                event_id,
                status,
                retry_count,
                last_retry_at,
                next_retry_at,
                last_error,
                is_deleted,
                created_at,
                updated_at
            )
            VALUES (
                :event_id,
                'pending',
                0,
                NULL,
                NULL,
                NULL,
                false,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (event_id) DO UPDATE
            SET status = 'pending',
                last_error = NULL,
                next_retry_at = NULL,
                updated_at = CURRENT_TIMESTAMP,
                is_deleted = false
            RETURNING id;
            """
        ),
        {"event_id": int(event_id)},
    )
    job_id = int(job_result.scalar_one())

    await session.execute(
        text(
            """
            INSERT INTO public.audit_log (user_id, action, entity, entity_id, payload)
            VALUES (
                :user_id,
                'approve',
                'approval_queue',
                :entity_id,
                :payload
            );
            """
        ),
        {
            "user_id": current_user_id,
            "entity_id": int(found_approval_id),
            "payload": f"approval_id={found_approval_id};event_id={event_id};job_id={job_id}",
        },
    )

    await session.commit()

    return ApprovalActionResult(
        approval_id=int(found_approval_id),
        event_id=int(event_id),
        job_id=job_id,
        acted_by=current_user_id,
        status="approved",
    )


async def reject_message(
    session: AsyncSession,
    approval_id: int,
    current_tg_id: int,
    comment: str | None = None,
) -> ApprovalActionResult:
    """
    Отклоняет заявку на согласование без создания job_queue.
    """
    current_user = await _get_current_user(session, current_tg_id)
    if not current_user:
        raise PermissionError("Пользователь не найден или отключен")

    current_user_id, role = current_user

    if role not in ("Admin", "Editor"):
        raise PermissionError("Отклонение доступно только ролям Admin и Editor")

    approval_query = text(
        """
        SELECT id, event_id, responsible_id, status
        FROM public.approval_queue
        WHERE id = :approval_id
          AND is_deleted = false
        FOR UPDATE;
        """
    )
    approval_result = await session.execute(approval_query, {"approval_id": approval_id})
    approval_row = approval_result.first()
    if not approval_row:
        raise ValueError("Заявка на согласование не найдена")

    found_approval_id, event_id, responsible_id, status = approval_row

    if status not in ("pending", "edited"):
        raise ValueError(f"Нельзя отклонить заявку со статусом '{status}'")

    if role != "Admin" and responsible_id != current_user_id:
        raise PermissionError("Отклонять заявку может только ответственный Editor или Admin")

    await session.execute(
        text(
            """
            UPDATE public.approval_queue
            SET status = 'rejected',
                comment = :comment,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :approval_id;
            """
        ),
        {"approval_id": int(found_approval_id), "comment": comment},
    )

    await session.execute(
        text(
            """
            INSERT INTO public.audit_log (user_id, action, entity, entity_id, payload)
            VALUES (
                :user_id,
                'reject',
                'approval_queue',
                :entity_id,
                :payload
            );
            """
        ),
        {
            "user_id": current_user_id,
            "entity_id": int(found_approval_id),
            "payload": f"approval_id={found_approval_id};event_id={event_id};comment={comment or ''}",
        },
    )

    await session.commit()

    return ApprovalActionResult(
        approval_id=int(found_approval_id),
        event_id=int(event_id),
        job_id=None,
        acted_by=current_user_id,
        status="rejected",
    )


async def edit_message(
    session: AsyncSession,
    approval_id: int,
    current_tg_id: int,
    new_text: str,
    comment: str | None = None,
) -> ApprovalActionResult:
    """
    Обновляет текст сообщения и оставляет заявку в статусе edited.
    """
    clean_text = new_text.strip()
    if not clean_text:
        raise ValueError("Новый текст сообщения не может быть пустым")

    current_user = await _get_current_user(session, current_tg_id)
    if not current_user:
        raise PermissionError("Пользователь не найден или отключен")

    current_user_id, role = current_user

    if role not in ("Admin", "Editor"):
        raise PermissionError("Редактирование доступно только ролям Admin и Editor")

    approval_query = text(
        """
        SELECT aq.id, aq.event_id, aq.responsible_id, aq.status
        FROM public.approval_queue aq
        WHERE aq.id = :approval_id
          AND aq.is_deleted = false
        FOR UPDATE;
        """
    )
    approval_result = await session.execute(approval_query, {"approval_id": approval_id})
    approval_row = approval_result.first()
    if not approval_row:
        raise ValueError("Заявка на согласование не найдена")

    found_approval_id, event_id, responsible_id, status = approval_row

    if status not in ("pending", "edited"):
        raise ValueError(f"Нельзя редактировать заявку со статусом '{status}'")

    if role != "Admin" and responsible_id != current_user_id:
        raise PermissionError("Редактировать заявку может только ответственный Editor или Admin")

    await session.execute(
        text(
            """
            UPDATE public.messages
            SET rendered_text = :rendered_text,
                approved_by = NULL,
                approved_at = NULL,
                sent_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE event_id = :event_id
              AND is_deleted = false;
            """
        ),
        {"rendered_text": clean_text, "event_id": int(event_id)},
    )

    await session.execute(
        text(
            """
            UPDATE public.approval_queue
            SET status = 'edited',
                comment = :comment,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :approval_id;
            """
        ),
        {"approval_id": int(found_approval_id), "comment": comment},
    )

    await session.execute(
        text(
            """
            INSERT INTO public.audit_log (user_id, action, entity, entity_id, payload)
            VALUES (
                :user_id,
                'edit',
                'messages',
                :entity_id,
                :payload
            );
            """
        ),
        {
            "user_id": current_user_id,
            "entity_id": int(event_id),
            "payload": f"approval_id={found_approval_id};event_id={event_id};comment={comment or ''}",
        },
    )

    await session.commit()

    return ApprovalActionResult(
        approval_id=int(found_approval_id),
        event_id=int(event_id),
        job_id=None,
        acted_by=current_user_id,
        status="edited",
    )
