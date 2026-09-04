from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .db_template_loader import DBTemplateLoader
from .birthday_generator import BirthdayGenerator
from .generation_types import GenerateRequest
from .template_blacklist import DEFAULT_BLACKLIST, fetch_blacklist_phrases
from .text_validator import validate_generated_text

from .llm_client import LLMClient
from .llm_generator import LLMGenerator


@dataclass
class TextServiceResult:
    rendered_text: str
    used_model: str                 # "deepseek-chat" или "templates"
    template_id: Optional[int] = None
    grammar_score: Optional[float] = None   # 0..1 (если есть)
    cache_hit: bool = False
    fallback_reason: Optional[str] = None


class TextService:
    """
    Единая точка: сначала пытаемся LLM (если есть ключ),
    при ошибке/отсутствии ключа — fallback на templates из БД.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_blacklist_phrases(self) -> list[str]:
        try:
            phrases = await fetch_blacklist_phrases(self.session)
        except Exception:
            phrases = []
        return phrases or DEFAULT_BLACKLIST

    @staticmethod
    def _ensure_text_valid(text: str, style: str, blacklist_phrases: list[str]) -> None:
        ok, reason = validate_generated_text(text, style, blacklist_phrases)
        if not ok:
            raise RuntimeError(f"generated_text_invalid:{reason}")

    @staticmethod
    def _available_template_fields(req: GenerateRequest) -> set[str]:
        fields = {
            "id",
            "contact_id",
            "name",
            "first_name",
            "holiday",
            "holiday_name",
            "channel",
            "style",
            "tone",
            "wish_phrase",
            "wish",
            "name_wish",
            "name_accs",
            "name_datv",
            "name_gen",
            "name_nomn",
            "template_id",
            "template_version",
        }
        for field_name in (
            "last_name",
            "middle_name",
            "full_name",
            "gender",
            "birthday",
            "age",
            "position",
            "company",
            "tz",
            "tg_username",
            "email",
            "preferred_channel",
            "default_style",
            "segment",
            "notes",
            "tg_chat_id",
            "is_active",
            "is_deleted",
            "created_at",
            "updated_at",
            "signature",
        ):
            if getattr(req, field_name, None) not in (None, ""):
                fields.add(field_name)
        if req.signature or req.company:
            fields.add("signature")
        return fields

    async def _generate_templates(self, req: GenerateRequest) -> TextServiceResult:
        loader = DBTemplateLoader(self.session)
        template = await loader.get_template(
            style=req.style,
            channel=req.channel,
            category=req.holiday_id,   # birthday/holiday
            language="ru",
            gender=req.gender,
            available_fields=self._available_template_fields(req),
        )
        if not template:
            raise RuntimeError(
                f"Не найден шаблон: style={req.style}, channel={req.channel}, category={req.holiday_id}"
            )

        generator = BirthdayGenerator()
        try:
            res = await generator.render(template, req)
        finally:
            generator.close()

        return TextServiceResult(
            rendered_text=res.rendered_text,
            used_model="templates",
            template_id=int(res.template_id) if res.template_id else None,
            grammar_score=res.grammar_score,  # 0..1
            cache_hit=bool(getattr(res, "cache_hit", False)),
        )

    async def _generate_llm(self, req: GenerateRequest) -> TextServiceResult:
        client = LLMClient.from_env()
        if not client:
            raise RuntimeError("DEEPSEEK_API_KEY не задан (env пустой)")

        gen = LLMGenerator(client, model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
        llm_res = await gen.generate(req)

        return TextServiceResult(
            rendered_text=llm_res.rendered_text,
            used_model=llm_res.used_model,
            template_id=None,
            grammar_score=None,
            cache_hit=llm_res.cache_hit,
        )

    async def generate(self, req: GenerateRequest) -> TextServiceResult:
        blacklist_phrases = await self._load_blacklist_phrases()
        if req.holiday_id == "holiday":
            template_result = await self._generate_templates(req)
            self._ensure_text_valid(template_result.rendered_text, req.style, blacklist_phrases)
            return template_result
        try:
            llm_result = await self._generate_llm(req)
            self._ensure_text_valid(llm_result.rendered_text, req.style, blacklist_phrases)
            return llm_result
        except Exception as e:
            if os.environ.get("TEXTGEN_LLM_DEBUG", "0") == "1":
                print(f"[LLM FAIL] {type(e).__name__}: {e}", file=sys.stderr)
            template_result = await self._generate_templates(req)
            self._ensure_text_valid(template_result.rendered_text, req.style, blacklist_phrases)
            template_result.fallback_reason = f"{type(e).__name__}: {e}"
            return template_result
