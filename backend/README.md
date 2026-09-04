# TimeWise Backend

Модуль отвечает за генерацию поздравлений, ежедневный поиск событий, согласование сообщений, очередь повторных отправок и экспорт метрик Prometheus.

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Минимально настройте `DATABASE_URL`. Для генерации через LLM также укажите `DEEPSEEK_API_KEY`.

## Запуск

```powershell
# Локальный пример генерации
python main.py

# Ежедневный планировщик
python -m src.scheduler.birthday_scheduler

# Worker реальной отправки
python -m src.workflow.run_worker_real_daemon

# Экспортер метрик
python -m src.monitoring.run_metrics_exporter
```

## Тесты

```powershell
python -m pytest
```

Дополнительные инструкции по мониторингу, доставке, резервному копированию и очередям находятся в `docs/`.
