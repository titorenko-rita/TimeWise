"""Фоновая обработка очереди отправки."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from db.repositories.approvals import expire_stale_approvals
from db.models import Contact, Event, EventLog, JobQueue, Message
from services.delivery import DeliveryResult, send_email_message, send_telegram_message

logger = logging.getLogger(__name__)


async def _pick_due_job(session: AsyncSession, *, channel: str = "Telegram") -> JobQueue | None:
    now = datetime.now()
    result = await session.execute(
        select(JobQueue)
        .join(Event, Event.id == JobQueue.event_id)
        .where(
            JobQueue.is_deleted == False,  # noqa: E712
            Event.is_deleted == False,  # noqa: E712
            Event.channel == channel,
            or_(
                JobQueue.status == "pending",
                and_(
                    JobQueue.status == "retry",
                    or_(JobQueue.next_retry_at.is_(None), JobQueue.next_retry_at <= now),
                ),
            ),
        )
        .order_by(
            JobQueue.next_retry_at.asc().nullsfirst(),
            JobQueue.updated_at.asc().nullsfirst(),
            JobQueue.id.asc(),
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    return result.scalars().first()


async def _latest_message(session: AsyncSession, event_id: int) -> Message | None:
    result = await session.execute(
        select(Message)
        .where(Message.event_id == event_id, Message.is_deleted == False)  # noqa: E712
        .order_by(desc(Message.id))
    )
    return result.scalars().first()


async def _deliver(bot: Bot, *, event: Event, contact: Contact, text: str) -> DeliveryResult:
    if event.channel == "Email":
        subject = f"TimeWise: поздравление на {event.date.isoformat()}"
        return await send_email_message(email=contact.email, subject=subject, text=text)
    return await send_telegram_message(
        bot,
        tg_chat_id=getattr(contact, "tg_chat_id", None),
        tg_username=contact.tg_username,
        text=text,
    )


async def _fail_without_retry(
    session: AsyncSession,
    *,
    job: JobQueue,
    event: Event | None,
    contact: Contact | None,
    error_message: str,
) -> None:
    now = datetime.now()
    job.status = "failed"
    job.last_retry_at = now
    job.last_error = error_message
    event_status = "failed"
    if event is not None:
        event.status = event_status
    if event is not None and contact is not None:
        session.add(
            EventLog(
                event_id=event.id,
                contact_id=contact.id,
                user_id=None,
                status=event_status,
                sent_at=None,
                duration_ms=0,
                error_message=error_message,
            )
        )


async def process_next_job(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    bot: Bot,
    retry_delays_min: list[int],
    channel: str = "Telegram",
) -> bool:
    async with sessionmaker() as session:
        async with session.begin():
            job = await _pick_due_job(session, channel=channel)
            if job is None:
                return False

            event = await session.get(Event, job.event_id)
            if event is None or event.is_deleted:
                await _fail_without_retry(
                    session,
                    job=job,
                    event=None,
                    contact=None,
                    error_message="Событие не найдено или удалено.",
                )
                return True

            contact = await session.get(Contact, event.contact_id)
            if contact is None or contact.is_deleted or not contact.is_active:
                await _fail_without_retry(
                    session,
                    job=job,
                    event=event,
                    contact=None,
                    error_message="Контакт не найден, удалён или выключен.",
                )
                return True

            message = await _latest_message(session, event.id)
            if message is None or not message.rendered_text.strip():
                await _fail_without_retry(
                    session,
                    job=job,
                    event=event,
                    contact=contact,
                    error_message="Подготовленное сообщение не найдено.",
                )
                return True

            result = await _deliver(bot, event=event, contact=contact, text=message.rendered_text)
            now = datetime.now()
            if result.success:
                job.status = "sent"
                job.last_error = None
                job.last_retry_at = now
                job.next_retry_at = None
                event.status = "sent"
                message.sent_at = now
                session.add(
                    EventLog(
                        event_id=event.id,
                        contact_id=contact.id,
                        user_id=None,
                        status="sent",
                        sent_at=now,
                        duration_ms=result.duration_ms,
                        error_message=None,
                    )
                )
                logger.info("Worker sent event_id=%s via %s.", event.id, event.channel)
                return True

            current_retry_count = int(job.retry_count or 0) + 1
            job.retry_count = current_retry_count
            job.last_retry_at = now
            job.last_error = result.error_message
            if current_retry_count <= len(retry_delays_min):
                delay_minutes = retry_delays_min[current_retry_count - 1]
                job.status = "retry"
                job.next_retry_at = now + timedelta(minutes=delay_minutes)
                event.status = "retry"
                log_status = "retry"
            else:
                job.status = "failed"
                job.next_retry_at = None
                event.status = "failed"
                log_status = "failed"

            session.add(
                EventLog(
                    event_id=event.id,
                    contact_id=contact.id,
                    user_id=None,
                    status=log_status,
                    sent_at=None,
                    duration_ms=result.duration_ms,
                    error_message=result.error_message,
                )
            )
            logger.warning(
                "Worker delivery failed for event_id=%s status=%s error=%s",
                event.id,
                job.status,
                result.error_message,
            )
            return True


async def process_stale_approvals(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    timeout_hours: int,
) -> int:
    async with sessionmaker() as session:
        async with session.begin():
            expired, errors = await expire_stale_approvals(session, timeout_hours=timeout_hours)
        if errors:
            logger.warning("Approval timeout processor finished with issues: %s", "; ".join(errors))
        if expired:
            logger.info("Approval timeout processor expired %s approval(s).", expired)
        return expired


async def run_worker_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    bot: Bot,
    retry_delays_min: list[int],
    poll_interval_sec: int,
    stop_event: asyncio.Event,
    channel: str = "Telegram",
) -> None:
    logger.info("Worker loop started with poll interval %ss for channel=%s.", poll_interval_sec, channel)
    last_stale_approvals_check_at: datetime | None = None
    stale_approvals_check_interval_sec = max(poll_interval_sec * 12, 60)
    while not stop_event.is_set():
        try:
            now = datetime.now()
            if (
                last_stale_approvals_check_at is None
                or (now - last_stale_approvals_check_at).total_seconds() >= stale_approvals_check_interval_sec
            ):
                await process_stale_approvals(
                    sessionmaker,
                    timeout_hours=settings.approval_timeout_hours,
                )
                last_stale_approvals_check_at = now
            processed = await process_next_job(
                sessionmaker,
                bot=bot,
                retry_delays_min=retry_delays_min,
                channel=channel,
            )
            if processed:
                continue
        except Exception as e:
            logger.exception("Worker loop iteration failed: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("Worker loop stopped.")


async def stop_worker_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
