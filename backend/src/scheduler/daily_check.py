from __future__ import annotations

from datetime import date, datetime, time

from dateutil.rrule import rrulestr
from sqlalchemy import text

from src.logging.logger import get_logger
from src.text_generator.db import SessionMaker
from src.text_generator.generate_for_event import generate_one_event


logger = get_logger("daily_check")


def _holiday_matches_today(
    *,
    holiday_date: date | None,
    holiday_rrule: str | None,
    target_date: date,
) -> bool:
    if holiday_rrule:
        try:
            dtstart = datetime.combine(holiday_date or target_date, time.min)
            rule = rrulestr(holiday_rrule, dtstart=dtstart)
            target_dt = datetime.combine(target_date, time.min)
            return rule.before(target_dt, inc=True) == target_dt
        except Exception:
            pass

    if holiday_date:
        return holiday_date.month == target_date.month and holiday_date.day == target_date.day

    return False


async def create_today_birthday_events(session, target_date: date) -> None:
    logger.info("Ищем контакты с ДР сегодня...")

    await session.execute(
        text(
            """
            INSERT INTO public.events (contact_id, holiday_id, date, channel, style, status)
            SELECT
                c.id,
                NULL,
                :target_date,
                c.preferred_channel,
                c.default_style,
                'pending'
            FROM public.contacts c
            WHERE EXTRACT(MONTH FROM c.birthday) = EXTRACT(MONTH FROM CAST(:target_date AS DATE))
              AND EXTRACT(DAY FROM c.birthday) = EXTRACT(DAY FROM CAST(:target_date AS DATE))
              AND (c.is_deleted = false OR c.is_deleted IS NULL)
              AND (c.is_active = true OR c.is_active IS NULL)
              AND NOT EXISTS (
                    SELECT 1
                    FROM public.events e
                    WHERE e.contact_id = c.id
                      AND e.date = CAST(:target_date AS DATE)
                      AND e.holiday_id IS NULL
                      AND COALESCE(e.is_deleted, false) = false
              );
            """
        ),
        {"target_date": target_date},
    )


async def _fetch_today_holidays(session, target_date: date) -> list[tuple[int, str | None]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, target_gender, date, rrule
                FROM public.holidays
                WHERE is_deleted = false
                ORDER BY
                    CASE WHEN target_gender IS NULL THEN 1 ELSE 0 END,
                    id DESC;
                """
            )
        )
    ).all()

    matched: list[tuple[int, str | None]] = []
    for holiday_id, target_gender, holiday_date, holiday_rrule in rows:
        if _holiday_matches_today(
            holiday_date=holiday_date,
            holiday_rrule=holiday_rrule,
            target_date=target_date,
        ):
            matched.append((int(holiday_id), str(target_gender) if target_gender else None))
    return matched


async def create_today_holiday_events(session, target_date: date) -> int:
    matched_holidays = await _fetch_today_holidays(session, target_date)
    inserted = 0

    for holiday_id, target_gender in matched_holidays:
        result = await session.execute(
            text(
                """
                INSERT INTO public.events (contact_id, holiday_id, date, channel, style, status)
                SELECT
                    c.id,
                    :holiday_id,
                    :target_date,
                    c.preferred_channel,
                    c.default_style,
                    'pending'
                FROM public.contacts c
                WHERE (c.is_deleted = false OR c.is_deleted IS NULL)
                  AND (c.is_active = true OR c.is_active IS NULL)
                  AND (
                        CAST(:target_gender AS VARCHAR(10)) IS NULL
                        OR c.gender = CAST(:target_gender AS VARCHAR(10))
                  )
                  AND NOT EXISTS (
                        SELECT 1
                        FROM public.events e
                        WHERE e.contact_id = c.id
                          AND e.date = CAST(:target_date AS DATE)
                          AND e.holiday_id IS NOT NULL
                          AND COALESCE(e.is_deleted, false) = false
                  );
                """
            ),
            {
                "holiday_id": holiday_id,
                "target_date": target_date,
                "target_gender": target_gender,
            },
        )
        inserted += int(result.rowcount or 0)

    return inserted


async def create_today_events(session, target_date: date) -> None:
    await create_today_birthday_events(session, target_date)
    inserted_holidays = await create_today_holiday_events(session, target_date)
    await session.commit()

    logger.info("События на сегодня созданы (если их не было)")
    if inserted_holidays:
        logger.info("Добавлено праздничных событий из holidays: %d", inserted_holidays)


async def daily_check() -> None:
    target_date = date.today()

    async with SessionMaker() as session:
        logger.info("🔍 Проверяем события на сегодня...")

        await create_today_events(session, target_date)

        result = await session.execute(
            text(
                """
                SELECT id
                FROM public.events
                WHERE date = CAST(:target_date AS DATE)
                  AND status IN ('pending', 'retry')
                  AND COALESCE(is_deleted, false) = false
                ORDER BY id ASC;
                """
            ),
            {"target_date": target_date},
        )
        events = result.fetchall()

        if not events:
            logger.info("Сегодня событий нет")
            return

        logger.info("Найдено событий: %d", len(events))

        for event in events:
            event_id = int(event[0])
            logger.info("Генерируем сообщение для event %s", event_id)
            try:
                await generate_one_event(session, event_id)
            except Exception as exc:
                logger.error("Ошибка генерации event %s: %s", event_id, exc)
