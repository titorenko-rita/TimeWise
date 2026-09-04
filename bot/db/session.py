"""Создание engine/session и инициализация схемы."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from db.models import Base


def _normalize_database_url(url: str) -> str:
    """
    Упрощаем настройку DATABASE_URL для async SQLAlchemy:
    - postgres://... -> postgresql+asyncpg://...
    - postgresql://... -> postgresql+asyncpg://...
    - sqlite://... -> sqlite+aiosqlite://...
    """
    if not url:
        return url

    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")

    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")

    if url.startswith("sqlite://") and "+aiosqlite" not in url:
        return "sqlite+aiosqlite://" + url.removeprefix("sqlite://")

    return url


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(
        _normalize_database_url(settings.database_url),
        echo=False,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы при старте (временный подход без миграций)."""
    if not settings.db_auto_create:
        return
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

