ALTER TABLE public.contacts
    ADD COLUMN IF NOT EXISTS tg_chat_id bigint;

CREATE UNIQUE INDEX IF NOT EXISTS ux_contacts_tg_chat_id
    ON public.contacts (tg_chat_id)
    WHERE tg_chat_id IS NOT NULL;
