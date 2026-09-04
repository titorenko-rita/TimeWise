from __future__ import annotations

import logging

from sqlalchemy import text

from config import settings
from db.session import get_sessionmaker

logger = logging.getLogger(__name__)


async def check_db_schema() -> None:
    """
    Проверяет, что бот подключился к ожидаемой Postgres-БД и что в ней есть
    нужные колонки для текущего MVP (users/contacts).

    Если схема не совпадает — поднимаем исключение, чтобы это было видно сразу при старте.
    """

    url = (settings.database_url or "").lower()
    if "postgresql" not in url and "postgres://" not in url:
        logger.info("DB schema check skipped (non-Postgres DATABASE_URL).")
        return

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        info = await session.execute(
            text(
                "select inet_server_addr() as ip, inet_server_port() as port, "
                "current_database() as db, current_user as usr"
            )
        )
        row = info.mappings().first()
        if row:
            logger.info(
                "DB connected: ip=%s port=%s db=%s user=%s",
                row.get("ip"),
                row.get("port"),
                row.get("db"),
                row.get("usr"),
            )

        required: dict[str, set[str]] = {
            "users": {"id", "tg_id", "role", "is_active", "created_at", "updated_at", "is_deleted"},
            "contacts": {
                "id",
                "last_name",
                "first_name",
                "middle_name",
                "gender",
                "birthday",
                "position",
                "company",
                "tz",
                "tg_username",
                "tg_chat_id",
                "email",
                "preferred_channel",
                "default_style",
                "segment",
                "notes",
                "is_active",
                "is_deleted",
                "created_at",
                "updated_at",
            },
            "events": {
                "id",
                "contact_id",
                "holiday_id",
                "date",
                "channel",
                "style",
                "status",
                "responsible_id",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "messages": {
                "id",
                "event_id",
                "template_id",
                "rendered_text",
                "approved_by",
                "approved_at",
                "sent_at",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "approval_queue": {
                "id",
                "event_id",
                "responsible_id",
                "status",
                "comment",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "job_queue": {
                "id",
                "event_id",
                "status",
                "retry_count",
                "last_retry_at",
                "next_retry_at",
                "last_error",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "event_log": {
                "id",
                "event_id",
                "contact_id",
                "user_id",
                "status",
                "sent_at",
                "duration_ms",
                "error_message",
                "created_at",
            },
            "templates": {
                "id",
                "channel",
                "style",
                "case",
                "category",
                "language",
                "body_text",
                "version",
                "is_active",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "template_blacklist": {
                "id",
                "phrase",
                "created_at",
                "updated_at",
                "is_deleted",
            },
            "holidays": {
                "id",
                "name",
                "date",
                "rrule",
                "target_gender",
                "category",
                "created_at",
                "updated_at",
                "is_deleted",
            },
        }

        missing: dict[str, set[str]] = {}
        for table, cols in required.items():
            res = await session.execute(
                text(
                    "select column_name "
                    "from information_schema.columns "
                    "where table_schema='public' and table_name=:t"
                ),
                {"t": table},
            )
            present = {r[0] for r in res.all()}
            miss = cols - present
            if miss:
                missing[table] = miss

        if missing:
            raise RuntimeError(f"DB schema mismatch. Missing columns: {missing}")

