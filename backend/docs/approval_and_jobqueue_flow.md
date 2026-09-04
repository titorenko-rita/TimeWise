# TimeWise: Approval и JobQueue

## approve_message()

1. Находим текущего пользователя по `users.tg_id`.
2. Проверяем роль:
   `Admin` может подтверждать всё.
   `Editor` может подтверждать только свои заявки.
3. Проверяем, что заявка в `approval_queue` имеет статус `pending` или `edited`.
4. Обновляем:
   `approval_queue.status = approved`
   `messages.approved_by = current_user.id`
   `messages.approved_at = now()`
5. Создаём или переоткрываем задачу в `job_queue` со статусом `pending`.
6. Пишем действие в `audit_log`.

## reject_message()

1. Находим пользователя по `users.tg_id`.
2. Проверяем, что это `Admin` или ответственный `Editor`.
3. Переводим `approval_queue.status` в `rejected`.
4. Сохраняем комментарий отказа в `approval_queue.comment`.
5. Ничего не создаём в `job_queue`.
6. Пишем отказ в `audit_log`.

## edit_message()

1. Находим пользователя по `users.tg_id`.
2. Проверяем права на редактирование.
3. Обновляем `messages.rendered_text`.
4. Сбрасываем `approved_by`, `approved_at`, `sent_at`.
5. Переводим заявку в `approval_queue.status = edited`.
6. Пишем факт редактирования в `audit_log`.

## worker_process_job()

1. Берём одну задачу из `job_queue` со статусом `pending/retry`.
2. Проверяем `next_retry_at`.
3. Собираем payload из `events`, `contacts`, `messages`.
4. Передаём payload в sender.
5. Если отправка успешна:
   `job_queue.status = sent|partial`
   `events.status = sent|partial`
   `messages.sent_at = now()` только для `sent`
   запись в `event_log`
6. Если отправка упала:
   увеличиваем `retry_count`
   сохраняем `last_retry_at`, `next_retry_at`, `last_error`
   переводим задачу в `retry` или `failed`
   пишем `event_log`

## Задачи для Маши

- Подключить кнопку `Approval` к `approve_message()`.
- Подключить кнопку `Править` к `edit_message()`.
- Подключить кнопку `Отменить` к `reject_message()`.
- Для `Editor` показывать только свои pending/edited заявки.
- В `Approval` добавить действия `Одобрить / Править / Отменить`.
- В `Рассылки` показывать данные из `job_queue`, а не из `approval_queue`.
- Для failed/retry задач выводить `last_error`, `retry_count`, `next_retry_at`.

## Задачи для backend

- Передавать в `approve_message()` реальный `current_tg_id`.
- Передавать в `edit_message()` и `reject_message()` реальный `current_tg_id`.
- Реализовать transport sender для Telegram/Email.
- Запускать `worker_process_job()` по расписанию или отдельным воркером.
- Убрать хардкод выбора Editor из генерации.
- Для локальной проверки использовать `src/workflow/demo_sender.py` и `src/workflow/run_worker_demo.py`.
- Для ручной проверки в БД использовать `docs/postgres_checks.sql`.
