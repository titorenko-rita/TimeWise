from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


DeliverySender = Callable[[dict], Awaitable["DeliveryResult"]]


@dataclass
class DeliveryResult:
    status: str
    error_message: str | None = None
    duration_ms: int | None = None


def _calc_next_retry_sql(retry_count: int) -> str:
    retry_minutes = {
        1: 15,
        2: 30,
    }.get(retry_count, 60)
    return f"CURRENT_TIMESTAMP + INTERVAL '{retry_minutes} minutes'"


async def worker_process_job(
    session: AsyncSession,
    sender: DeliverySender,
) -> DeliveryResult | None:
    """
    Берёт одну задачу из очереди и пытается её отправить.
    sender должен вернуть DeliveryResult(status='sent'|'partial'|'failed', ...)
    """
    job_query = text(
        """
        SELECT
            jq.id,
            jq.event_id,
            jq.retry_count,
            e.contact_id,
            e.date,
            e.channel,
            e.style,
            c.first_name,
            c.last_name,
            c.middle_name,
            c.tg_username,
            c.tg_chat_id,
            c.email,
            m.rendered_text
        FROM public.job_queue jq
        JOIN public.events e ON e.id = jq.event_id
        JOIN public.contacts c ON c.id = e.contact_id
        JOIN public.messages m ON m.event_id = e.id
        WHERE jq.is_deleted = false
          AND jq.status IN ('pending', 'retry')
          AND (jq.next_retry_at IS NULL OR jq.next_retry_at <= CURRENT_TIMESTAMP)
          AND e.is_deleted = false
          AND (c.is_deleted = false OR c.is_deleted IS NULL)
          AND (m.is_deleted = false OR m.is_deleted IS NULL)
        ORDER BY
            CASE WHEN jq.status = 'pending' THEN 0 ELSE 1 END,
            jq.created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED;
        """
    )
    job_result = await session.execute(job_query)
    job = job_result.first()
    if not job:
        return None

    (
        job_id,
        event_id,
        retry_count,
        contact_id,
        event_date,
        channel,
        style,
        first_name,
        last_name,
        middle_name,
        tg_username,
        tg_chat_id,
        email,
        rendered_text,
    ) = job

    payload = {
        "job_id": int(job_id),
        "event_id": int(event_id),
        "contact_id": int(contact_id),
        "event_date": event_date,
        "channel": channel,
        "style": style,
        "first_name": first_name,
        "last_name": last_name,
        "middle_name": middle_name,
        "tg_username": tg_username,
        "tg_chat_id": tg_chat_id,
        "email": email,
        "rendered_text": rendered_text,
    }

    try:
        result = await sender(payload)
    except Exception as exc:
        result = DeliveryResult(status="failed", error_message=str(exc))

    final_status = result.status if result.status in ("sent", "partial", "failed") else "failed"

    if final_status == "failed":
        new_retry_count = int(retry_count) + 1
        if new_retry_count >= 4:
            queue_status = "failed"
            next_retry_expr = "NULL"
        else:
            queue_status = "retry"
            next_retry_expr = _calc_next_retry_sql(new_retry_count)

        await session.execute(
            text(
                f"""
                UPDATE public.job_queue
                SET status = :status,
                    retry_count = :retry_count,
                    last_retry_at = CURRENT_TIMESTAMP,
                    next_retry_at = {next_retry_expr},
                    last_error = :last_error,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :job_id;
                """
            ),
            {
                "status": queue_status,
                "retry_count": new_retry_count,
                "last_error": result.error_message,
                "job_id": int(job_id),
            },
        )

        await session.execute(
            text(
                """
                UPDATE public.events
                SET status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :event_id;
                """
            ),
            {"status": queue_status, "event_id": int(event_id)},
        )

        await session.execute(
            text(
                """
                INSERT INTO public.event_log (
                    event_id,
                    contact_id,
                    user_id,
                    status,
                    sent_at,
                    duration_ms,
                    error_message
                )
                VALUES (
                    :event_id,
                    :contact_id,
                    NULL,
                    :status,
                    NULL,
                    :duration_ms,
                    :error_message
                );
                """
            ),
            {
                "event_id": int(event_id),
                "contact_id": int(contact_id),
                "status": queue_status,
                "duration_ms": result.duration_ms,
                "error_message": result.error_message,
            },
        )

        await session.commit()
        return DeliveryResult(status=queue_status, error_message=result.error_message, duration_ms=result.duration_ms)

    await session.execute(
        text(
            """
            UPDATE public.job_queue
            SET status = :status,
                last_error = :last_error,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id;
            """
        ),
        {
            "status": final_status,
            "last_error": result.error_message if final_status == "partial" else None,
            "job_id": int(job_id),
        },
    )

    await session.execute(
        text(
            """
            UPDATE public.events
            SET status = :status,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :event_id;
            """
        ),
        {"status": final_status, "event_id": int(event_id)},
    )

    if final_status == "sent":
        await session.execute(
            text(
                """
                UPDATE public.messages
                SET sent_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = :event_id
                  AND is_deleted = false;
                """
            ),
            {"event_id": int(event_id)},
        )

    await session.execute(
        text(
            """
            INSERT INTO public.event_log (
                event_id,
                contact_id,
                user_id,
                status,
                sent_at,
                duration_ms,
                error_message
            )
            VALUES (
                :event_id,
                :contact_id,
                NULL,
                :status,
                CURRENT_TIMESTAMP,
                :duration_ms,
                :error_message
            );
            """
        ),
        {
            "event_id": int(event_id),
            "contact_id": int(contact_id),
            "status": final_status,
            "duration_ms": result.duration_ms,
            "error_message": result.error_message,
        },
    )

    await session.commit()
    return result
