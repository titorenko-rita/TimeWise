from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Iterable

from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily
from sqlalchemy import text

from src.text_generator.db import SessionMaker


HISTOGRAM_BUCKETS_MS = [50, 100, 250, 500, 1_000, 2_000, 5_000, 10_000, 30_000, 60_000]


def _bucketize(values: list[int], buckets: list[int]) -> tuple[list[tuple[str, int]], int, float]:
    total_count = len(values)
    total_sum = float(sum(values))
    cumulative_counts = [
        (str(bucket), sum(1 for value in values if value <= bucket))
        for bucket in buckets
    ]
    cumulative_counts.append(("+Inf", total_count))
    return cumulative_counts, total_count, total_sum


def _normalize_error_reason(message: str | None) -> str:
    if not message:
        return "unknown"

    normalized = " ".join(str(message).strip().split())
    if len(normalized) > 120:
        return normalized[:117] + "..."
    return normalized


class TimeWiseDbCollector:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="timewise-prometheus-loop",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _table_exists(self, session, table_name: str) -> bool:
        result = await session.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": table_name},
        )
        return result.scalar_one_or_none() is not None

    async def _column_exists(self, session, table_schema: str, table_name: str, column_name: str) -> bool:
        result = await session.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :table_schema
                  AND table_name = :table_name
                  AND column_name = :column_name
                LIMIT 1;
                """
            ),
            {
                "table_schema": table_schema,
                "table_name": table_name,
                "column_name": column_name,
            },
        )
        return result.first() is not None

    async def _collect_async(self) -> Iterable[object]:
        metrics: list[object] = []

        async with SessionMaker() as session:
            queue_rows = (
                await session.execute(
                    text(
                        """
                        SELECT status, COUNT(*)
                        FROM public.job_queue
                        WHERE is_deleted = false
                        GROUP BY status;
                        """
                    )
                )
            ).all()

            queue_metric = GaugeMetricFamily(
                "timewise_queue_jobs",
                "Current number of jobs in queue by status",
                labels=["status"],
            )
            for status, count in queue_rows:
                queue_metric.add_metric([str(status)], int(count))
            metrics.append(queue_metric)

            delivery_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            COALESCE(e.channel, 'unknown') AS channel,
                            COALESCE(el.status, 'unknown') AS status,
                            COUNT(*) AS total
                        FROM public.event_log el
                        LEFT JOIN public.events e ON e.id = el.event_id
                        GROUP BY COALESCE(e.channel, 'unknown'), COALESCE(el.status, 'unknown');
                        """
                    )
                )
            ).all()

            delivery_metric = CounterMetricFamily(
                "timewise_delivery_attempts_total",
                "Total delivery attempts by channel and status",
                labels=["channel", "status"],
            )
            for channel, status, total in delivery_rows:
                delivery_metric.add_metric([str(channel), str(status)], int(total))
            metrics.append(delivery_metric)

            worker_duration_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            COALESCE(e.channel, 'unknown') AS channel,
                            COALESCE(el.status, 'unknown') AS status,
                            el.duration_ms
                        FROM public.event_log el
                        LEFT JOIN public.events e ON e.id = el.event_id
                        WHERE el.duration_ms IS NOT NULL;
                        """
                    )
                )
            ).all()

            worker_histogram = HistogramMetricFamily(
                "timewise_worker_duration_ms",
                "Worker processing time in milliseconds",
                labels=["channel", "status"],
            )
            worker_groups: dict[tuple[str, str], list[int]] = {}
            for channel, status, duration_ms in worker_duration_rows:
                worker_groups.setdefault((str(channel), str(status)), []).append(int(duration_ms))

            for (channel, status), durations in worker_groups.items():
                buckets, total_count, total_sum = _bucketize(durations, HISTOGRAM_BUCKETS_MS)
                worker_histogram.add_metric([channel, status], buckets=buckets, sum_value=total_sum)
            metrics.append(worker_histogram)

            error_rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            COALESCE(e.channel, 'unknown') AS channel,
                            COALESCE(el.error_message, 'unknown') AS error_message,
                            COUNT(*) AS total
                        FROM public.event_log el
                        LEFT JOIN public.events e ON e.id = el.event_id
                        WHERE el.error_message IS NOT NULL
                          AND NULLIF(BTRIM(el.error_message), '') IS NOT NULL
                        GROUP BY COALESCE(e.channel, 'unknown'), COALESCE(el.error_message, 'unknown');
                        """
                    )
                )
            ).all()

            error_metric = CounterMetricFamily(
                "timewise_delivery_errors_total",
                "Total delivery errors by channel and reason",
                labels=["channel", "reason"],
            )
            for channel, error_message, total in error_rows:
                error_metric.add_metric(
                    [str(channel), _normalize_error_reason(error_message)],
                    int(total),
                )
            metrics.append(error_metric)

            has_generation_duration = await self._column_exists(
                session,
                "public",
                "events",
                "generation_duration_ms",
            )
            has_generation_status = await self._column_exists(
                session,
                "public",
                "events",
                "generation_status",
            )
            has_generation_engine = await self._column_exists(
                session,
                "public",
                "events",
                "generation_engine",
            )
            has_generation_cache_hit = await self._column_exists(
                session,
                "public",
                "events",
                "generation_cache_hit",
            )

            if has_generation_duration and has_generation_status:
                generation_rows = (
                    await session.execute(
                        text(
                            """
                            SELECT
                                COALESCE(e.generation_status, 'unknown') AS status,
                                COALESCE(e.generation_engine, 'unknown') AS engine,
                                COALESCE(m.used_model, 'unknown') AS used_model,
                                COALESCE(e.generation_cache_hit, false) AS cache_hit,
                                e.generation_duration_ms
                            FROM public.events e
                            LEFT JOIN public.messages m ON m.event_id = e.id
                            WHERE e.generation_duration_ms IS NOT NULL;
                            """
                        )
                    )
                ).all()

                generation_total_metric = CounterMetricFamily(
                    "timewise_generation_runs_total",
                    "Total generation runs by status, engine, model and cache flag",
                    labels=["status", "engine", "used_model", "cache_hit"],
                )
                generation_totals: dict[tuple[str, str, str, str], int] = {}
                generation_groups: dict[tuple[str, str, str, str], list[int]] = {}
                for status, engine, used_model, cache_hit, duration_ms in generation_rows:
                    labels = (
                        str(status),
                        str(engine),
                        str(used_model),
                        "true" if bool(cache_hit) else "false",
                    )
                    generation_totals[labels] = generation_totals.get(labels, 0) + 1
                    if duration_ms is not None:
                        generation_groups.setdefault(labels, []).append(int(duration_ms))
                for labels, total in generation_totals.items():
                    generation_total_metric.add_metric(list(labels), total)
                metrics.append(generation_total_metric)

                generation_histogram = HistogramMetricFamily(
                    "timewise_generation_duration_ms",
                    "Generation time in milliseconds",
                    labels=["status", "engine", "used_model", "cache_hit"],
                )
                for labels, durations in generation_groups.items():
                    buckets, total_count, total_sum = _bucketize(durations, HISTOGRAM_BUCKETS_MS)
                    generation_histogram.add_metric(list(labels), buckets=buckets, sum_value=total_sum)
                metrics.append(generation_histogram)

            generation_log_metric = GaugeMetricFamily(
                "timewise_generation_metrics_enabled",
                "Whether generation columns are available on existing tables",
            )
            generation_log_metric.add_metric(
                [],
                1 if has_generation_duration and has_generation_status else 0,
            )
            metrics.append(generation_log_metric)

        exporter_metric = GaugeMetricFamily(
            "timewise_exporter_start_time_seconds",
            "Unix timestamp when the exporter process started",
        )
        exporter_metric.add_metric([], self.started_at)
        metrics.append(exporter_metric)

        return metrics

    def collect(self) -> Iterable[object]:
        future = asyncio.run_coroutine_threadsafe(self._collect_async(), self._loop)
        return future.result(timeout=30)


def run_exporter() -> None:
    host = os.environ.get("TIMEWISE_METRICS_HOST", "0.0.0.0")
    port = int(os.environ.get("TIMEWISE_METRICS_PORT", "8001"))
    collector = TimeWiseDbCollector()
    REGISTRY.register(collector)
    start_http_server(port=port, addr=host)
    print(f"TimeWise Prometheus exporter listening on http://{host}:{port}/metrics")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    run_exporter()
