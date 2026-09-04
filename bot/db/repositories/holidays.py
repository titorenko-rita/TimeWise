from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Holiday


@dataclass(frozen=True, slots=True)
class HolidayRow:
    id: int
    name: str
    date: date | None
    rrule: str | None
    target_gender: str | None
    category: str | None


async def list_holidays(session: AsyncSession, *, limit: int = 200) -> list[HolidayRow]:
    result = await session.execute(
        select(Holiday)
        .where(Holiday.is_deleted == False)  # noqa: E712
        .order_by(Holiday.date.asc().nulls_last(), Holiday.id.asc())
        .limit(limit)
    )
    holidays = result.scalars().all()
    return [
        HolidayRow(
            id=holiday.id,
            name=holiday.name,
            date=holiday.date,
            rrule=holiday.rrule,
            target_gender=holiday.target_gender,
            category=holiday.category,
        )
        for holiday in holidays
    ]


async def create_holiday(
    session: AsyncSession,
    *,
    name: str,
    date_value: date | None,
    rrule: str | None,
    target_gender: str | None,
    category: str | None,
) -> Holiday:
    holiday = Holiday(
        name=name,
        date=date_value,
        rrule=rrule,
        target_gender=target_gender,
        category=category,
        is_deleted=False,
    )
    session.add(holiday)
    await session.commit()
    await session.refresh(holiday)
    return holiday
