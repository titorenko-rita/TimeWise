# Real Delivery

## Email

Для реальной отправки email добавь в `.env`:

```env
EMAIL_SMTP_HOST=smtp.example.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=your_login
EMAIL_SMTP_PASSWORD=your_password
EMAIL_FROM=your_email@example.com
EMAIL_USE_STARTTLS=1
EMAIL_USE_SSL=0
```

Что отправляется сейчас:

- plain-text версия письма
- HTML-версия письма с базовым макетом
- PDF-вложение с тем же поздравлением

PDF формируется на стороне приложения во время отправки письма.

Запуск реального worker:

```powershell
python -m src.workflow.run_worker_real
```

Для постоянной обработки очереди и автоматических retry используйте daemon-режим:

```powershell
python -m src.workflow.run_worker_real_daemon
```

По умолчанию daemon проверяет `job_queue` каждые 10 секунд и сам подхватывает задачи
со статусами `pending/retry`, когда наступает `next_retry_at`.

## Telegram

Для Telegram одного `tg_username` недостаточно.
Боту нужен числовой `chat_id` / `user_id` того пользователя, который уже начал диалог с ботом.

Чтобы включить Telegram по-настоящему, нужно:

1. Хранить у контакта `tg_chat_id`.
2. Сохранять его после `/start` или отдельной команды привязки.
3. Передавать `tg_chat_id` в sender.
4. Добавить в `.env`:

```env
TELEGRAM_BOT_TOKEN=...
```
