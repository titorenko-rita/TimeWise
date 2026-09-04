from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Boolean, Integer, String, Text, TIMESTAMP
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TemplateORM(Base):
    __tablename__ = "templates"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="Telegram")
    style: Mapped[str] = mapped_column(String(50), nullable=False)
    case: Mapped[str] = mapped_column("case", String(50), nullable=False)  # зарезервированное слово -> "case"
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True, default="ru")
    target_gender: Mapped[str | None] = mapped_column(String(20), nullable=True)

    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[str | None] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[str | None] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
