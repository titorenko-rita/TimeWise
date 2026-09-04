from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .template_model import Template

# ВАЖНО:
# TemplateORM — это SQLAlchemy модель таблицы templates из общего проекта.
# Её импорт будет из вашего слоя БД (куда Илья положит модели).
# Пример пути: from src.db.models import TemplateORM
# Я ниже оставлю как заглушку, чтобы ты подставила правильный импорт.
from src.db.models import TemplateORM  # <-- Илья/вы подставите реальный путь


class DBTemplateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def pick_one(
        self,
        *,
        style: str,
        channel: str,
        category: str,
        language: str = "ru",
    ) -> Optional[Template]:
        stmt = (
            select(TemplateORM)
            .where(TemplateORM.is_active.is_(True))
            .where(TemplateORM.is_deleted.is_(False))
            .where(TemplateORM.style == style)
            .where(TemplateORM.channel == channel)
            .where(TemplateORM.category == category)
            .where(TemplateORM.language == language)
            .order_by(TemplateORM.version.desc(), TemplateORM.id.asc())
            .limit(20)
        )

        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return None

        # Выбираем случайный из лучших/самых свежих версий (limit 20)
        import random
        row = random.choice(rows)

        return Template(
            id=row.id,
            channel=row.channel,
            style=row.style,
            category=row.category,
            language=row.language,
            body_text=row.body_text,
            version=row.version,
            case=getattr(row, "case", None),  # если поля case нет в БД — ок
            is_active=row.is_active,
        )
