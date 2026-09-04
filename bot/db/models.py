"""SQLAlchemy модели для БД TimeWise."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """Пользователи бота и роли доступа (см. ТЗ, таблица Users)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # admin/editor/viewer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Contact(Base):
    """Контакты получателей (см. ТЗ, таблица Contacts)."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(64), nullable=False)

    gender: Mapped[str] = mapped_column(String(16), nullable=False)  # male/female/unknown
    birthday: Mapped[date] = mapped_column(Date, nullable=False)

    position: Mapped[str] = mapped_column(String(128), nullable=False)
    company: Mapped[str] = mapped_column(String(128), nullable=False)

    tz: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. Europe/Moscow

    tg_username: Mapped[str] = mapped_column(String(64), nullable=False)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    preferred_channel: Mapped[str] = mapped_column(String(16), nullable=False)  # telegram/email/unknown
    default_style: Mapped[str] = mapped_column(String(16), nullable=False)  # friendly/business/official/unknown

    segment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Holiday(Base):
    """Праздники и памятные даты."""

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rrule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Template(Base):
    """Шаблоны сообщений."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    style: Mapped[str] = mapped_column(String(16), nullable=False)
    case: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TemplateBlacklist(Base):
    """Черный список слов и фраз для шаблонов."""

    __tablename__ = "template_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phrase: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Event(Base):
    """События, требующие подготовки и отправки сообщений."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    holiday_id: Mapped[int | None] = mapped_column(ForeignKey("holidays.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    style: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Message(Base):
    """Подготовленные сообщения для событий."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"), nullable=True)
    rendered_text: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    used_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    grammar_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ApprovalQueue(Base):
    """Очередь согласования сообщений."""

    __tablename__ = "approval_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class JobQueue(Base):
    """Очередь отправки сообщений."""

    __tablename__ = "job_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class EventLog(Base):
    """Лог попыток отправки."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )


class AuditLog(Base):
    """Аудит действий пользователей и системных операций."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )
