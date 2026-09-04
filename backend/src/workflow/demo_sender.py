from __future__ import annotations

from .worker_service import DeliveryResult


async def demo_sender(payload: dict) -> DeliveryResult:
    """
    Тестовая заглушка вместо реального Telegram/Email sender.

    Поведение:
    - если в тексте есть [fail], возвращает failed
    - если в тексте есть [partial], возвращает partial
    - иначе возвращает sent
    """
    text = str(payload.get("rendered_text", ""))

    if "[fail]" in text.lower():
        return DeliveryResult(
            status="failed",
            error_message="Demo sender forced failure",
            duration_ms=120,
        )

    if "[partial]" in text.lower():
        return DeliveryResult(
            status="partial",
            error_message="Demo sender partial delivery",
            duration_ms=90,
        )

    return DeliveryResult(
        status="sent",
        error_message=None,
        duration_ms=75,
    )
