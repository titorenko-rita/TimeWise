from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

APP_UP = Gauge("timewise_app_up", "Application liveness flag.")
SERVICE_ENABLED = Gauge("timewise_service_enabled", "Enabled embedded services.", ["service"])
UPDATES_TOTAL = Counter("timewise_updates_total", "Incoming Telegram updates.", ["kind"])
HANDLER_ERRORS_TOTAL = Counter("timewise_handler_errors_total", "Unhandled bot errors.", ["source"])
SCHEDULER_CYCLES_TOTAL = Counter("timewise_scheduler_cycles_total", "Scheduler cycle executions.", ["status"])
SCHEDULER_CYCLE_DURATION_SECONDS = Histogram(
    "timewise_scheduler_cycle_duration_seconds",
    "Scheduler cycle duration in seconds.",
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
SCHEDULER_CONTACTS_SCANNED_TOTAL = Counter(
    "timewise_scheduler_contacts_scanned_total",
    "Contacts checked by the scheduler.",
)
SCHEDULER_EVENTS_CREATED_TOTAL = Counter(
    "timewise_scheduler_events_created_total",
    "Events created by the scheduler.",
)
SCHEDULER_MESSAGES_CREATED_TOTAL = Counter(
    "timewise_scheduler_messages_created_total",
    "Messages created by the scheduler.",
)
SCHEDULER_APPROVALS_CREATED_TOTAL = Counter(
    "timewise_scheduler_approvals_created_total",
    "Approval rows created by the scheduler.",
)
WORKER_JOBS_TOTAL = Counter("timewise_worker_jobs_total", "Worker job outcomes.", ["status", "channel"])
WORKER_JOB_DURATION_SECONDS = Histogram(
    "timewise_worker_job_duration_seconds",
    "Worker job processing duration in seconds.",
    ["channel"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
QUEUE_ITEMS = Gauge("timewise_queue_items", "Current queue sizes.", ["queue", "status"])
TABLE_ROWS = Gauge("timewise_table_rows", "Current row counts by table.", ["table"])
DB_POLL_SUCCESS = Gauge("timewise_db_poll_success", "Last DB metrics polling status.")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, level: str, log_file_path: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root_logger.addHandler(console)

    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(file_handler)


def set_app_up(value: bool) -> None:
    APP_UP.set(1 if value else 0)


def set_service_enabled(service: str, enabled: bool) -> None:
    SERVICE_ENABLED.labels(service=service).set(1 if enabled else 0)


def record_update(kind: str) -> None:
    UPDATES_TOTAL.labels(kind=kind).inc()


def record_handler_error(source: str) -> None:
    HANDLER_ERRORS_TOTAL.labels(source=source).inc()


def record_scheduler_cycle(*, stats, duration_seconds: float, ok: bool) -> None:
    SCHEDULER_CYCLES_TOTAL.labels(status="success" if ok else "error").inc()
    SCHEDULER_CYCLE_DURATION_SECONDS.observe(duration_seconds)
    if ok:
        SCHEDULER_CONTACTS_SCANNED_TOTAL.inc(int(getattr(stats, "contacts_scanned", 0)))
        SCHEDULER_EVENTS_CREATED_TOTAL.inc(int(getattr(stats, "events_created", 0)))
        SCHEDULER_MESSAGES_CREATED_TOTAL.inc(int(getattr(stats, "messages_created", 0)))
        SCHEDULER_APPROVALS_CREATED_TOTAL.inc(int(getattr(stats, "approvals_created", 0)))


def record_worker_job(*, channel: str, status: str, duration_seconds: float) -> None:
    WORKER_JOBS_TOTAL.labels(status=status, channel=channel).inc()
    WORKER_JOB_DURATION_SECONDS.labels(channel=channel).observe(duration_seconds)


async def _metrics_handler(_: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


async def _health_handler(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def start_observability_server(*, host: str, port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/metrics", _metrics_handler)
    app.router.add_get("/healthz", _health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.getLogger(__name__).info("Observability server started on http://%s:%s", host, port)
    return runner


async def stop_observability_server(runner: web.AppRunner | None) -> None:
    if runner is not None:
        await runner.cleanup()


async def refresh_db_metrics(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    queue_map = {
        "approval_pending": (
            "approval",
            "pending",
            "select count(*) from public.approval_queue where coalesce(is_deleted,false)=false and status='pending'",
        ),
        "approval_edited": (
            "approval",
            "edited",
            "select count(*) from public.approval_queue where coalesce(is_deleted,false)=false and status='edited'",
        ),
        "approval_today_pending": (
            "approval",
            "today_pending",
            "select count(*) from public.approval_queue aq "
            "join public.events e on e.id=aq.event_id "
            "where coalesce(aq.is_deleted,false)=false and e.date=current_date and aq.status in ('pending','edited')",
        ),
        "job_pending": (
            "job",
            "pending",
            "select count(*) from public.job_queue where coalesce(is_deleted,false)=false and status='pending'",
        ),
        "job_retry": (
            "job",
            "retry",
            "select count(*) from public.job_queue where coalesce(is_deleted,false)=false and status='retry'",
        ),
        "job_failed": (
            "job",
            "failed",
            "select count(*) from public.job_queue where coalesce(is_deleted,false)=false and status='failed'",
        ),
        "job_sent": (
            "job",
            "sent",
            "select count(*) from public.job_queue where coalesce(is_deleted,false)=false and status='sent'",
        ),
    }
    table_queries = {
        "contacts": "select count(*) from public.contacts where coalesce(is_deleted,false)=false",
        "events": "select count(*) from public.events where coalesce(is_deleted,false)=false",
        "messages": "select count(*) from public.messages where coalesce(is_deleted,false)=false",
        "approval_queue": "select count(*) from public.approval_queue where coalesce(is_deleted,false)=false",
        "job_queue": "select count(*) from public.job_queue where coalesce(is_deleted,false)=false",
        "templates": "select count(*) from public.templates where coalesce(is_deleted,false)=false",
        "users": "select count(*) from public.users where coalesce(is_deleted,false)=false",
    }

    async with sessionmaker() as session:
        for queue, status, sql in queue_map.values():
            value = await _scalar_count(session, sql)
            QUEUE_ITEMS.labels(queue=queue, status=status).set(value)
        for table_name, sql in table_queries.items():
            value = await _scalar_count(session, sql)
            TABLE_ROWS.labels(table=table_name).set(value)


async def _scalar_count(session: AsyncSession, sql: str) -> int:
    result = await session.execute(text(sql))
    return int(result.scalar_one() or 0)


async def run_db_metrics_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    stop_event: asyncio.Event,
    interval_sec: int,
) -> None:
    logger = logging.getLogger(__name__)
    while not stop_event.is_set():
        try:
            await refresh_db_metrics(sessionmaker)
            DB_POLL_SUCCESS.set(1)
        except Exception as e:
            DB_POLL_SUCCESS.set(0)
            logger.exception("DB metrics refresh failed: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue


def timed() -> tuple[float, callable[[], float]]:
    started_at = perf_counter()
    return started_at, lambda: perf_counter() - started_at
