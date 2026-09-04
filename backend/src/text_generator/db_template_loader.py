import random
import string
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .template_model import Template
from .db_models import TemplateORM


# DB -> internal (как у тебя в генераторе)
STYLE_DB_TO_INTERNAL = {
    "Business": "business",
    "Official": "official",
    "Friendly": "friendly",
}
CHANNEL_DB_TO_INTERNAL = {
    "Telegram": "telegram",
    "Email": "email",
    "SMS": "sms",
}
CASE_DB_TO_INTERNAL = {
    "Nominative": "nomn",
    "Genitive": "gent",
    "Dative": "datv",
    "Accusative": "accs",
    "Instrumental": "ablt",
    "Prepositional": "loct",
}

# internal -> DB (для where условий)
STYLE_INTERNAL_TO_DB = {v: k for k, v in STYLE_DB_TO_INTERNAL.items()}
CHANNEL_INTERNAL_TO_DB = {v: k for k, v in CHANNEL_DB_TO_INTERNAL.items()}


class DBTemplateLoader:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_gender(gender: str | None) -> str | None:
        value = (gender or "").strip().lower()
        if value in {"male", "m", "man", "м", "муж", "мужской"}:
            return "Male"
        if value in {"female", "f", "woman", "ж", "жен", "женский"}:
            return "Female"
        return None

    @staticmethod
    def _extract_placeholders(body_text: str) -> set[str]:
        formatter = string.Formatter()
        fields: set[str] = set()
        for _, field_name, _, _ in formatter.parse(body_text):
            if field_name:
                fields.add(field_name)
        return fields

    @classmethod
    def _row_matches_available_fields(
        cls,
        row: TemplateORM,
        available_fields: set[str] | None,
    ) -> bool:
        if not available_fields:
            return True
        required_fields = cls._extract_placeholders(row.body_text)
        return required_fields.issubset(available_fields)

    @classmethod
    def _pick_row(
        cls,
        rows: list[TemplateORM],
        gender: str | None,
        available_fields: set[str] | None = None,
    ) -> Optional[TemplateORM]:
        filtered_rows = [row for row in rows if cls._row_matches_available_fields(row, available_fields)]
        if not filtered_rows:
            filtered_rows = rows
        if not filtered_rows:
            return None

        normalized_gender = cls._normalize_gender(gender)
        exact_gender_rows = [row for row in filtered_rows if row.target_gender == normalized_gender] if normalized_gender else []
        neutral_rows = [row for row in filtered_rows if not row.target_gender]
        fallback_rows = filtered_rows

        pool = exact_gender_rows or neutral_rows or fallback_rows
        max_version = max((row.version or 1) for row in pool)
        latest_rows = [row for row in pool if (row.version or 1) == max_version]
        return random.choice(latest_rows)

    async def get_template(
        self,
        *,
        style: str,
        channel: str = "telegram",
        category: str = "birthday",
        language: str = "ru",
        gender: str | None = None,
        available_fields: set[str] | None = None,
    ) -> Optional[Template]:
        db_style = STYLE_INTERNAL_TO_DB.get(style, style)
        db_channel = CHANNEL_INTERNAL_TO_DB.get(channel, channel)

        stmt = (
            select(TemplateORM)
            .where(TemplateORM.is_active.is_(True))
            .where(TemplateORM.is_deleted.is_(False))
            .where(TemplateORM.style == db_style)
            .where(TemplateORM.channel == db_channel)
            .where(TemplateORM.category == category)
            .where(TemplateORM.language == language)
            .order_by(TemplateORM.version.desc(), TemplateORM.id.asc())
            .limit(50)
        )

        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return None

        row = self._pick_row(rows, gender, available_fields=available_fields)
        if not row:
            return None

        return Template(
            id=row.id,
            channel=CHANNEL_DB_TO_INTERNAL.get(row.channel, row.channel),
            style=STYLE_DB_TO_INTERNAL.get(row.style, row.style),
            category=row.category or "",
            language=row.language or "ru",
            body_text=row.body_text,
            version=row.version,
            case=CASE_DB_TO_INTERNAL.get(row.case),
            target_gender=row.target_gender,
            is_active=row.is_active,
        )
