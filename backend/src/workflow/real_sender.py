from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from time import perf_counter

import httpx

from .email_rendering import (
    build_email_html,
    build_email_pdf_bytes,
    build_email_text,
    build_full_name,
)
from .worker_service import DeliveryResult


def _save_debug_eml(msg: EmailMessage, payload: dict) -> None:
    debug_dir = str(os.environ.get("EMAIL_DEBUG_SAVE_DIR") or "").strip()
    if not debug_dir:
        return

    target_dir = Path(debug_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    event_id = str(payload.get("event_id") or "event")
    file_path = target_dir / f"timewise-email-{event_id}.eml"
    file_path.write_bytes(bytes(msg))


def _build_email_subject(payload: dict) -> str:
    full_name = build_full_name(payload, case="gent")
    event_date = payload.get("event_date")
    return f"TimeWise: поздравление для {full_name} ({event_date})"


async def send_email(payload: dict) -> DeliveryResult:
    host = os.environ.get("EMAIL_SMTP_HOST")
    port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    username = os.environ.get("EMAIL_SMTP_USER")
    password = os.environ.get("EMAIL_SMTP_PASSWORD")
    sender = os.environ.get("EMAIL_FROM")

    if not host or not username or not password or not sender:
        return DeliveryResult(
            status="failed",
            error_message="SMTP is not configured. Set EMAIL_SMTP_HOST, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_FROM",
            duration_ms=None,
        )

    recipient = str(payload.get("email") or "").strip()
    if not recipient:
        return DeliveryResult(
            status="failed",
            error_message="Recipient email is empty",
            duration_ms=None,
        )

    msg = EmailMessage()
    msg["Subject"] = _build_email_subject(payload)
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(build_email_text(payload))
    msg.add_alternative(build_email_html(payload), subtype="html")

    try:
        pdf_filename, pdf_bytes = build_email_pdf_bytes(payload)
    except Exception as exc:
        return DeliveryResult(
            status="failed",
            error_message=f"PDF build failed: {exc}",
            duration_ms=None,
        )

    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )
    _save_debug_eml(msg, payload)

    use_ssl = os.environ.get("EMAIL_USE_SSL", "0") == "1"
    started_at = perf_counter()

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if os.environ.get("EMAIL_USE_STARTTLS", "1") == "1":
                    server.starttls()
                    server.ehlo()
                server.login(username, password)
                server.send_message(msg)
    except Exception as exc:
        return DeliveryResult(
            status="failed",
            error_message=f"SMTP send failed: {exc}",
            duration_ms=int((perf_counter() - started_at) * 1000),
        )

    return DeliveryResult(
        status="sent",
        error_message=None,
        duration_ms=int((perf_counter() - started_at) * 1000),
    )


async def send_telegram(payload: dict) -> DeliveryResult:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return DeliveryResult(
            status="failed",
            error_message="TELEGRAM_BOT_TOKEN is not configured",
            duration_ms=None,
        )

    # Telegram Bot API cannot send a direct message by username alone.
    # For real delivery you need a numeric chat_id/user_id from the user
    # who has already started the bot.
    chat_id = payload.get("tg_chat_id")
    if not chat_id:
        return DeliveryResult(
            status="failed",
            error_message="Telegram delivery requires tg_chat_id/user_id; tg_username alone is not enough",
            duration_ms=None,
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": str(payload.get("rendered_text") or "").strip(),
    }
    started_at = perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=body)
            if response.status_code >= 400:
                return DeliveryResult(
                    status="failed",
                    error_message=f"Telegram API error {response.status_code}: {response.text}",
                    duration_ms=int((perf_counter() - started_at) * 1000),
                )
    except Exception as exc:
        return DeliveryResult(
            status="failed",
            error_message=f"Telegram send failed: {exc}",
            duration_ms=int((perf_counter() - started_at) * 1000),
        )

    return DeliveryResult(
        status="sent",
        error_message=None,
        duration_ms=int((perf_counter() - started_at) * 1000),
    )


async def real_sender(payload: dict) -> DeliveryResult:
    channel = str(payload.get("channel") or "").strip().lower()

    if channel == "email":
        return await send_email(payload)

    if channel == "telegram":
        return await send_telegram(payload)

    return DeliveryResult(
        status="failed",
        error_message=f"Unsupported channel: {payload.get('channel')}",
        duration_ms=None,
    )
