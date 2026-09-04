-- 1. Посмотреть текущие заявки на согласование.
SELECT aq.id,
       aq.event_id,
       aq.responsible_id,
       aq.status,
       aq.comment,
       aq.updated_at
FROM public.approval_queue aq
WHERE aq.is_deleted = false
ORDER BY aq.id DESC;

-- 2. Посмотреть текст и информацию по сообщению.
SELECT m.id,
       m.event_id,
       m.rendered_text,
       m.approved_by,
       m.approved_at,
       m.sent_at,
       m.updated_at
FROM public.messages m
WHERE m.is_deleted = false
ORDER BY m.id DESC;

-- 3. Проверить, что после approve появилась задача в job_queue.
SELECT jq.id,
       jq.event_id,
       jq.status,
       jq.retry_count,
       jq.last_retry_at,
       jq.next_retry_at,
       jq.last_error,
       jq.updated_at
FROM public.job_queue jq
WHERE jq.is_deleted = false
ORDER BY jq.id DESC;

-- 4. Проверить итоговый статус event.
SELECT e.id,
       e.contact_id,
       e.status,
       e.updated_at
FROM public.events e
WHERE e.is_deleted = false
ORDER BY e.id DESC;

-- 5. Проверить журнал действий approve/edit/reject.
SELECT al.id,
       al.user_id,
       al.action,
       al.entity,
       al.entity_id,
       al.payload,
       al.ts
FROM public.audit_log al
ORDER BY al.id DESC;

-- 6. Проверить журнал отправок worker.
SELECT el.id,
       el.event_id,
       el.contact_id,
       el.status,
       el.sent_at,
       el.duration_ms,
       el.error_message,
       el.created_at
FROM public.event_log el
ORDER BY el.id DESC;

-- 7. Удобная сводка по одному событию.
-- Замени :event_id на нужный id в PGAdmin вручную.
SELECT
    e.id AS event_id,
    e.status AS event_status,
    aq.id AS approval_id,
    aq.status AS approval_status,
    jq.id AS job_id,
    jq.status AS job_status,
    jq.retry_count,
    jq.next_retry_at,
    jq.last_error,
    m.approved_by,
    m.approved_at,
    m.sent_at
FROM public.events e
LEFT JOIN public.approval_queue aq ON aq.event_id = e.id AND aq.is_deleted = false
LEFT JOIN public.job_queue jq ON jq.event_id = e.id AND jq.is_deleted = false
LEFT JOIN public.messages m ON m.event_id = e.id AND m.is_deleted = false
WHERE e.id = :event_id;
