# TimeWise

TimeWise — система автоматизации поздравлений: она хранит контакты и события, генерирует тексты, отправляет сообщения и позволяет управлять процессом через Telegram-бота.

## Состав проекта

| Модуль | Назначение |
| --- | --- |
| [`backend/`](backend/) | Генерация текстов, планировщик событий, очередь отправки и мониторинг |
| [`bot/`](bot/) | Telegram-интерфейс на Aiogram для контактов, шаблонов, согласований и отчётов |
| [`database/`](database/) | Схема PostgreSQL без пользовательских и тестовых данных |

Оба приложения работают с одной базой данных. Бэкенд создаёт тексты и обрабатывает события, а бот предоставляет интерфейс управления и может запускать встроенные планировщик и worker.

## Быстрый запуск

Требования: Python 3.11+, PostgreSQL 16+ и Telegram Bot Token.

### 1. База данных

```powershell
createdb timewise
psql -d timewise -f database/schema.sql
```

Скрипт `database/schema.sql` создан в режиме `schema-only`: в нём нет записей из рабочей базы.

### 2. Бэкенд

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Заполните `.env`, затем запустите нужный процесс:

```powershell
python main.py
python -m src.scheduler.birthday_scheduler
python -m src.workflow.run_worker_real_daemon
```

### 3. Telegram-бот

В отдельном терминале:

```powershell
cd bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python bot.py
```

Подробное руководство по командам и ролям находится в [`bot/README.md`](bot/README.md).

## Конфигурация

Секреты задаются только через локальные `.env`-файлы. В репозитории находятся безопасные примеры:

- `backend/.env.example` — подключение к PostgreSQL, DeepSeek, SMTP и метрики;
- `bot/.env.example` — токен Telegram, администраторы, БД, планировщик и worker.

Файлы `.env`, локальные базы, дампы, логи, кэши, резервные копии и виртуальные окружения исключены из Git.

## Проверка

```powershell
cd backend
python -m pytest
```

## Структура

```text
TimeWise/
├── backend/          # генерация, планировщик, worker, тесты и мониторинг
├── bot/              # Telegram-бот, обработчики, сервисы и модели
├── database/
│   ├── README.md
│   └── schema.sql    # только структура PostgreSQL
├── .gitignore
└── README.md
```

## Безопасность данных

Репозиторий не содержит токенов, паролей, локальной SQLite-базы, архивов, резервных копий или записей из PostgreSQL. Перед любым новым коммитом не добавляйте `.env` и дампы с данными.
