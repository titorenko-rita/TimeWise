import os
from dataclasses import dataclass, field
from typing import List
from urllib.request import getproxies

from dotenv import load_dotenv


load_dotenv()


def _parse_admin_ids(raw: str | None) -> List[int]:
    if not raw:
        return []
    result: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError:
            continue
    return result


def _parse_int_list(raw: str | None, *, default: list[int]) -> list[int]:
    if not raw:
        return list(default)
    result: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError:
            continue
    return result or list(default)


def _detect_telegram_proxy() -> str:
    for key in ("TELEGRAM_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = os.getenv(key, "").strip()
        if value:
            return value

    proxies = getproxies()
    for key in ("https", "http"):
        value = str(proxies.get(key, "")).strip()
        if value:
            return value

    return ""


@dataclass(slots=True)
class Settings:
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    admin_ids: List[int] = field(
        default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS"))
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///timewise.db"
        )
    )
    db_auto_create: bool = field(
        default_factory=lambda: os.getenv("DB_AUTO_CREATE", "1").strip() not in {"0", "false", "False"}
    )
    scheduler_enabled: bool = field(
        default_factory=lambda: os.getenv("SCHEDULER_ENABLED", "1").strip() not in {"0", "false", "False"}
    )
    scheduler_run_on_startup: bool = field(
        default_factory=lambda: os.getenv("SCHEDULER_RUN_ON_STARTUP", "1").strip() not in {"0", "false", "False"}
    )
    scheduler_daily_time: str = field(
        default_factory=lambda: os.getenv("SCHEDULER_DAILY_TIME", "09:00").strip() or "09:00"
    )
    worker_enabled: bool = field(
        default_factory=lambda: os.getenv("WORKER_ENABLED", "1").strip() not in {"0", "false", "False"}
    )
    worker_poll_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("WORKER_POLL_INTERVAL_SEC", "5") or "5")
    )
    approval_timeout_hours: int = field(
        default_factory=lambda: int(os.getenv("APPROVAL_TIMEOUT_HOURS", "8") or "8")
    )
    retry_delays_min: list[int] = field(
        default_factory=lambda: _parse_int_list(os.getenv("RETRY_DELAYS_MIN"), default=[15, 30, 60])
    )
    default_message_language: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MESSAGE_LANGUAGE", "ru").strip() or "ru"
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO")
    observability_enabled: bool = field(
        default_factory=lambda: os.getenv("OBSERVABILITY_ENABLED", "1").strip() not in {"0", "false", "False"}
    )
    observability_host: str = field(
        default_factory=lambda: os.getenv("OBSERVABILITY_HOST", "0.0.0.0").strip() or "0.0.0.0"
    )
    observability_port: int = field(
        default_factory=lambda: int(os.getenv("OBSERVABILITY_PORT", "9108") or "9108")
    )
    observability_metrics_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("OBSERVABILITY_METRICS_INTERVAL_SEC", "30") or "30")
    )
    log_file_path: str = field(default_factory=lambda: os.getenv("LOG_FILE_PATH", "logs/timewise.jsonl").strip())
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "").strip())
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587") or "587"))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", "").strip())
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", "").strip())
    smtp_from_email: str = field(default_factory=lambda: os.getenv("SMTP_FROM_EMAIL", "").strip())
    smtp_use_tls: bool = field(
        default_factory=lambda: os.getenv("SMTP_TLS", "1").strip() not in {"0", "false", "False"}
    )
    telegram_proxy: str = field(default_factory=_detect_telegram_proxy)

    def validate(self) -> None:
        if not self.bot_token:
            raise ValueError(
                "Не задан токен бота. Убедитесь, что переменная окружения BOT_TOKEN заполнена."
            )
        hhmm = self.scheduler_daily_time.split(":")
        if len(hhmm) != 2:
            raise ValueError("SCHEDULER_DAILY_TIME должен быть в формате HH:MM.")
        try:
            hour = int(hhmm[0])
            minute = int(hhmm[1])
        except ValueError as e:
            raise ValueError("SCHEDULER_DAILY_TIME должен содержать часы и минуты числами.") from e
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("SCHEDULER_DAILY_TIME должен быть в диапазоне 00:00-23:59.")
        if self.worker_poll_interval_sec < 1:
            raise ValueError("WORKER_POLL_INTERVAL_SEC должен быть >= 1.")
        if self.approval_timeout_hours < 1:
            raise ValueError("APPROVAL_TIMEOUT_HOURS must be >= 1.")
        if not self.retry_delays_min:
            raise ValueError("RETRY_DELAYS_MIN не должен быть пустым.")
        if self.observability_port < 1 or self.observability_port > 65535:
            raise ValueError("OBSERVABILITY_PORT должен быть в диапазоне 1-65535.")
        if self.observability_metrics_interval_sec < 5:
            raise ValueError("OBSERVABILITY_METRICS_INTERVAL_SEC должен быть >= 5.")


settings = Settings()
settings.validate()
