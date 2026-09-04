# Мониторинг TimeWise

## Что добавлено

- nullable-поля генерации в `public.events`
- Prometheus exporter: `src/monitoring/run_metrics_exporter.py`
- конфиг Prometheus: `monitoring/prometheus.yml`
- заготовка Grafana dashboard: `docs/timewise_grafana_dashboard.json`

## Какие метрики доступны

- `timewise_queue_jobs{status}`: текущее состояние очереди
- `timewise_delivery_attempts_total{channel,status}`: объём отправок, retry, ошибок, partial
- `timewise_worker_duration_ms_*`: время работы воркера
- `timewise_delivery_errors_total{channel,reason}`: причины ошибок
- `timewise_generation_runs_total{status,engine,used_model,cache_hit}`: генерации текста
- `timewise_generation_duration_ms_*`: время генерации текста
- `timewise_generation_metrics_enabled`: применена ли миграция колонок генерации
- `timewise_exporter_start_time_seconds`: uptime exporter-процесса

## Как запустить

1. Импортировать актуальную схему из `../database/schema.sql`.
2. Запустить exporter:

```powershell
python -m src.monitoring.run_metrics_exporter
```

3. Запустить Prometheus:

```powershell
prometheus.exe --config.file=monitoring/prometheus.yml
```

Если `prometheus.exe` не добавлен в `PATH`, укажите полный путь к нему, например:

```powershell
C:\tools\prometheus\prometheus.exe --config.file=.\monitoring\prometheus.yml
```

4. В Grafana добавить data source Prometheus:
   `http://localhost:9090`
5. Импортировать dashboard из `docs/timewise_grafana_dashboard.json`.

## Почему генерация может быть пустой

Если в `/metrics` есть только:

- `timewise_generation_metrics_enabled 1`

но нет строк у `timewise_generation_runs_total` и `timewise_generation_duration_ms`, это значит, что после миграции ещё не было новых запусков генерации, которые заполнили:

- `events.generation_status`
- `events.generation_duration_ms`
- `events.generation_engine`
- `events.generation_cache_hit`

Нужно заново прогнать генерацию хотя бы для нескольких событий.

## Полезные запросы для Grafana

- Queue Status:
  `sum by (status) (timewise_queue_jobs)`
- Delivery Overview:
  `sum by (status) (timewise_delivery_attempts_total)`
- Generation Time P95:
  `histogram_quantile(0.95, sum by (le) (timewise_generation_duration_ms_bucket))`
- Top Errors:
  `topk(10, sum by (reason) (timewise_delivery_errors_total))`
- Uptime:
  `time() - timewise_exporter_start_time_seconds`

Если Prometheus был пересоздан и история очистилась, панели на `rate(...)` и `increase(...)`
могут временно показывать `No data`. Запросы выше устойчивее после перезапуска, потому что
опираются на накопленные значения с момента старта exporter'а.

Полезные запросы для дополнительных панелей:

- Errors by Channel:
  `sum by (channel) (timewise_delivery_errors_total)`
- Telegram vs Email:
  `sum by (channel) (timewise_delivery_attempts_total)`
- Error rate alert:
  `sum(timewise_delivery_errors_total) > 0`
- Uptime alert:
  `time() - timewise_exporter_start_time_seconds`
