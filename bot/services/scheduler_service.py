"""Фоновое планирование поздравлений."""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import date
from time import perf_counter

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import ApprovalQueue, Contact, Event, Message, User
from observability import record_scheduler_cycle
from services.delivery import send_telegram_message
from services.message_builder import build_message_for_contact

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SchedulerRunStats:
    contacts_scanned: int = 0
    events_created: int = 0
    messages_created: int = 0
    approvals_created: int = 0


@dataclass(frozen=True, slots=True)
class ResponsibleUser:
    id: int
    tg_id: int
    role: str


@dataclass(frozen=True, slots=True)
class ApprovalNotification:
    approval_id: int
    event_id: int
    event_date: date
    channel: str
    style: str
    contact_name: str
    responsible_tg_id: int
    rendered_text: str


async def _pick_responsible_user(session: AsyncSession, admin_ids: list[int]) -> ResponsibleUser | None:
    result = await session.execute(
        select(User)
        .where(
            User.role == "Editor",
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.id.asc())
    )
    user = result.scalars().first()
    if user is not None:
        return ResponsibleUser(id=user.id, tg_id=user.tg_id, role=user.role)

    if admin_ids:
        result = await session.execute(
            select(User)
            .where(
                User.tg_id.in_(admin_ids),
                User.is_deleted == False,  # noqa: E712
                User.is_active == True,  # noqa: E712
            )
            .order_by(User.id.asc())
        )
        user = result.scalars().first()
        if user is not None:
            return ResponsibleUser(id=user.id, tg_id=user.tg_id, role=user.role)

    result = await session.execute(
        select(User)
        .where(
            User.role == "Admin",
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
        .order_by(User.id.asc())
    )
    user = result.scalars().first()
    if user is None:
        return None
    return ResponsibleUser(id=user.id, tg_id=user.tg_id, role=user.role)


async def _latest_message(session: AsyncSession, event_id: int) -> Message | None:
    result = await session.execute(
        select(Message)
        .where(Message.event_id == event_id, Message.is_deleted == False)  # noqa: E712
        .order_by(desc(Message.id))
    )
    return result.scalars().first()


async def _latest_approval(session: AsyncSession, event_id: int) -> ApprovalQueue | None:
    result = await session.execute(
        select(ApprovalQueue)
        .where(ApprovalQueue.event_id == event_id, ApprovalQueue.is_deleted == False)  # noqa: E712
        .order_by(desc(ApprovalQueue.id))
    )
    return result.scalars().first()


def _contact_display_name(contact: Contact) -> str:
    return " ".join(part for part in [contact.last_name, contact.first_name, contact.middle_name] if part).strip()


def _approval_notification_text(notification: ApprovalNotification) -> str:
    preview = (notification.rendered_text or "").strip()
    if len(preview) > 1200:
        preview = preview[:1197].rstrip() + "..."
    return (
        "✉️ Новая заявка на согласование\n\n"
        f"approval_id: <code>{notification.approval_id}</code>\n"
        f"event_id: <code>{notification.event_id}</code>\n"
        f"дата: <b>{notification.event_date.isoformat()}</b>\n"
        f"канал/стиль: <b>{html.escape(notification.channel)}</b> / <b>{html.escape(notification.style)}</b>\n"
        f"получатель: <b>{html.escape(notification.contact_name)}</b>\n\n"
        "Предпросмотр:\n"
        f"<pre>{html.escape(preview or '(пусто)')}</pre>\n\n"
        "Откройте раздел Approval в боте, чтобы одобрить, править или отменить заявку."
    )


async def _notify_created_approvals(bot: Bot | None, notifications: list[ApprovalNotification]) -> None:
    if bot is None:
        return
    for notification in notifications:
        result = await send_telegram_message(
            bot,
            tg_chat_id=notification.responsible_tg_id,
            text=_approval_notification_text(notification),
        )
        if not result.success:
            logger.warning(
                "Failed to notify responsible user tg_id=%s for approval_id=%s: %s",
                notification.responsible_tg_id,
                notification.approval_id,
                result.error_message,
            )


async def _ensure_birthday_event(
    session: AsyncSession,
    *,
    contact: Contact,
    target_date: date,
    responsible_user: ResponsibleUser | None,
) -> tuple[bool, bool, bool, ApprovalNotification | None]:
    channel = contact.preferred_channel or ("Email" if contact.email else "Telegram")
    style = contact.default_style or "Friendly"

    result = await session.execute(
        select(Event)
        .where(
            Event.contact_id == contact.id,
            Event.date == target_date,
            Event.channel == channel,
            Event.style == style,
            Event.is_deleted == False,  # noqa: E712
        )
        .order_by(desc(Event.id))
    )
    event = result.scalars().first()
    created_event = False
    created_message = False
    created_approval = False

    if event is None:
        event = Event(
            contact_id=contact.id,
            holiday_id=None,
            date=target_date,
            channel=channel,
            style=style,
            status="pending",
            responsible_id=responsible_user.id if responsible_user is not None else None,
            is_deleted=False,
        )
        session.add(event)
        await session.flush()
        created_event = True

    message = await _latest_message(session, event.id)
    if message is None:
        prepared = await build_message_for_contact(
            session,
            contact=contact,
            event_date=target_date,
            channel=channel,
            style=style,
            holiday_name="днем рождения",
        )
        message = Message(
            event_id=event.id,
            template_id=prepared.template_id,
            rendered_text=prepared.rendered_text,
            is_deleted=False,
        )
        session.add(message)
        created_message = True

    approval = await _latest_approval(session, event.id)
    notification: ApprovalNotification | None = None
    if approval is None:
        approval = ApprovalQueue(
            event_id=event.id,
            responsible_id=responsible_user.id if responsible_user is not None else None,
            status="pending",
            comment="Создано планировщиком автоматически.",
            is_deleted=False,
        )
        session.add(approval)
        await session.flush()
        created_approval = True
        if responsible_user is not None:
            notification = ApprovalNotification(
                approval_id=approval.id,
                event_id=event.id,
                event_date=target_date,
                channel=channel,
                style=style,
                contact_name=_contact_display_name(contact) or f"contact {contact.id}",
                responsible_tg_id=responsible_user.tg_id,
                rendered_text=message.rendered_text,
            )

    return created_event, created_message, created_approval, notification


async def run_scheduling_cycle(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    admin_ids: list[int],
    bot: Bot | None = None,
    target_date: date | None = None,
) -> SchedulerRunStats:
    started_at = perf_counter()
    current_date = target_date or date.today()
    stats = SchedulerRunStats()
    notifications: list[ApprovalNotification] = []
    try:
        async with sessionmaker() as session:
            result = await session.execute(
                select(Contact).where(Contact.is_deleted == False, Contact.is_active == True)  # noqa: E712
            )
            contacts = result.scalars().all()
            responsible_user = await _pick_responsible_user(session, admin_ids)

            scanned = 0
            created_events = 0
            created_messages = 0
            created_approvals = 0
            for contact in contacts:
                if contact.birthday.month != current_date.month or contact.birthday.day != current_date.day:
                    continue
                scanned += 1
                event_created, message_created, approval_created, notification = await _ensure_birthday_event(
                    session,
                    contact=contact,
                    target_date=current_date,
                    responsible_user=responsible_user,
                )
                created_events += int(event_created)
                created_messages += int(message_created)
                created_approvals += int(approval_created)
                if notification is not None:
                    notifications.append(notification)

            await session.commit()
            stats = SchedulerRunStats(
                contacts_scanned=scanned,
                events_created=created_events,
                messages_created=created_messages,
                approvals_created=created_approvals,
            )
    except Exception:
        record_scheduler_cycle(stats=stats, duration_seconds=perf_counter() - started_at, ok=False)
        raise
    await _notify_created_approvals(bot, notifications)
    record_scheduler_cycle(stats=stats, duration_seconds=perf_counter() - started_at, ok=True)

    logger.info(
        "Scheduler cycle finished: scanned=%s events=%s messages=%s approvals=%s",
        stats.contacts_scanned,
        stats.events_created,
        stats.messages_created,
        stats.approvals_created,
    )
    return stats


def start_scheduler_service(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    bot: Bot | None,
    admin_ids: list[int],
    daily_time: str,
    run_on_startup: bool,
) -> AsyncIOScheduler:
    hour_raw, minute_raw = daily_time.split(":", maxsplit=1)
    hour = int(hour_raw)
    minute = int(minute_raw)

    scheduler = AsyncIOScheduler()

    def _spawn_cycle() -> None:
        asyncio.create_task(run_scheduling_cycle(sessionmaker, admin_ids=admin_ids, bot=bot))

    scheduler.add_job(
        _spawn_cycle,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily-birthday-scheduler",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler service started for %02d:%02d.", hour, minute)
    if run_on_startup:
        asyncio.create_task(run_scheduling_cycle(sessionmaker, admin_ids=admin_ids, bot=bot))
    return scheduler
