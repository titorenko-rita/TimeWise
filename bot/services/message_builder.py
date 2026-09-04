"""Подготовка текста поздравления для событий."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Contact, Template


@dataclass(frozen=True, slots=True)
class PreparedMessage:
    rendered_text: str
    template_id: int | None


def _render_text(body_text: str, ctx: dict[str, str]) -> str:
    text = body_text.replace("{{", "{").replace("}}", "}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return ctx.get(key, match.group(0))

    return re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", repl, text).strip()


def _fallback_message(contact: Contact, *, holiday_name: str, style: str) -> str:
    full_name = " ".join(
        part for part in [contact.first_name, contact.middle_name, contact.last_name] if part
    ).strip()
    if style == "Official":
        return (
            f"Уважаемый(ая) {full_name or contact.first_name}! "
            f"Примите искренние поздравления с {holiday_name}. "
            "Желаем здоровья, успехов и благополучия."
        )
    if style == "Business":
        return (
            f"{contact.first_name}, поздравляем вас с {holiday_name}! "
            "Желаем продуктивной работы, развития и хорошего настроения."
        )
    return (
        f"{contact.first_name}, с {holiday_name}! "
        "Пусть день будет радостным, теплым и запоминающимся."
    )


def _category_candidates(holiday_name: str | None) -> list[str]:
    names = ["birthday", "Birthday"]
    if holiday_name:
        lowered = holiday_name.strip().lower()
        names.extend([lowered, holiday_name.strip()])
    return names


async def _pick_template(
    session: AsyncSession,
    *,
    channel: str,
    style: str,
    holiday_name: str,
) -> Template | None:
    result = await session.execute(
        select(Template)
        .where(
            Template.is_deleted == False,  # noqa: E712
            Template.is_active == True,  # noqa: E712
            Template.channel == channel,
            Template.style == style,
            Template.language == settings.default_message_language,
        )
        .order_by(desc(Template.version), desc(Template.id))
    )
    templates = result.scalars().all()
    if not templates:
        return None

    candidates = {value.lower() for value in _category_candidates(holiday_name)}
    for template in templates:
        if template.category.lower() in candidates:
            return template
    return templates[0]


async def build_message_for_contact(
    session: AsyncSession,
    *,
    contact: Contact,
    event_date: date,
    channel: str,
    style: str,
    holiday_name: str = "днем рождения",
) -> PreparedMessage:
    template = await _pick_template(
        session,
        channel=channel,
        style=style,
        holiday_name=holiday_name,
    )
    context = {
        "first_name": contact.first_name or "",
        "last_name": contact.last_name or "",
        "middle_name": contact.middle_name or "",
        "company": contact.company or "",
        "position": contact.position or "",
        "holiday": holiday_name,
        "tone": style,
        "signature": "TimeWise",
        "event_date": event_date.isoformat(),
    }
    if template is None:
        return PreparedMessage(
            rendered_text=_fallback_message(contact, holiday_name=holiday_name, style=style),
            template_id=None,
        )
    return PreparedMessage(
        rendered_text=_render_text(template.body_text, context),
        template_id=template.id,
    )
