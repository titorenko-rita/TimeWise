import hashlib

from sqlalchemy import text

from .db import SessionMaker


class TextCache:
    def __init__(self, session_factory=SessionMaker):
        self.session_factory = session_factory

    def _make_key(
        self,
        *,
        contact_id,
        holiday_id,
        style,
        template_id,
        template_version,
        name,
        wish_phrase,
        context_key="",
        engine="template",   # "template" | "llm"
    ):
        raw = (
            f"{engine}|{contact_id}|{holiday_id}|{style}|{template_id}|v{template_version}|"
            f"{name}|{wish_phrase}|{context_key}"
        )
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    async def get(self, **kwargs):
        key = self._make_key(**kwargs)
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT generated_text
                    FROM public.text_cache
                    WHERE hash_key = :hash_key
                      AND is_deleted = false
                    LIMIT 1;
                    """
                ),
                {"hash_key": key},
            )
            row = result.first()
            if not row:
                return None

            await session.execute(
                text(
                    """
                    UPDATE public.text_cache
                    SET used_count = COALESCE(used_count, 0) + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE hash_key = :hash_key;
                    """
                ),
                {"hash_key": key},
            )
            await session.commit()
            return row[0]

    async def set(self, text_value: str, **kwargs):
        key = self._make_key(**kwargs)
        async with self.session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO public.text_cache (
                        hash_key,
                        generated_text,
                        created_at,
                        updated_at,
                        used_count,
                        is_deleted
                    )
                    VALUES (
                        :hash_key,
                        :generated_text,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        0,
                        false
                    )
                    ON CONFLICT (hash_key) DO UPDATE
                    SET generated_text = EXCLUDED.generated_text,
                        updated_at = CURRENT_TIMESTAMP,
                        is_deleted = false;
                    """
                ),
                {
                    "hash_key": key,
                    "generated_text": text_value,
                },
            )
            await session.commit()
        return key
