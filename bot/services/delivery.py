"""Отправка сообщений в каналы связи."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage

from aiogram import Bot

from config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    success: bool
    duration_ms: int
    error_message: str | None = None


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _telegram_target(raw: str | int | None) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    candidate = raw.strip()
    if candidate.startswith("@"):
        candidate = candidate[1:]
    if candidate.lstrip("-").isdigit():
        return int(candidate)
    return None


async def send_telegram_message(
    bot: Bot,
    *,
    tg_chat_id: int | str | None = None,
    tg_username: str | None = None,
    text: str,
) -> DeliveryResult:
    start = time.perf_counter()
    chat_id = _telegram_target(tg_chat_id)
    if chat_id is None:
        chat_id = _telegram_target(tg_username)
    if chat_id is None:
        return DeliveryResult(
            success=False,
            duration_ms=_elapsed_ms(start),
            error_message=(
                "Для Telegram-отправки нужен chat_id. "
                "Обычного username недостаточно: бот не может написать пользователю первым только по @username."
            ),
        )
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return DeliveryResult(success=True, duration_ms=_elapsed_ms(start))
    except Exception as e:
        logger.exception("Telegram delivery failed: %s", e)
        return DeliveryResult(success=False, duration_ms=_elapsed_ms(start), error_message=str(e))


def _send_email_sync(*, to_email: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email
    msg.set_content(text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def send_email_message(*, email: str | None, subject: str, text: str) -> DeliveryResult:
    start = time.perf_counter()
    if not email:
        return DeliveryResult(
            success=False,
            duration_ms=_elapsed_ms(start),
            error_message="У контакта не заполнен email.",
        )
    if not settings.smtp_host:
        return DeliveryResult(
            success=False,
            duration_ms=_elapsed_ms(start),
            error_message="SMTP не настроен: заполните SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD.",
        )
    try:
        await asyncio.to_thread(_send_email_sync, to_email=email, subject=subject, text=text)
        return DeliveryResult(success=True, duration_ms=_elapsed_ms(start))
    except Exception as e:
        logger.exception("Email delivery failed: %s", e)
        return DeliveryResult(success=False, duration_ms=_elapsed_ms(start), error_message=str(e))
