import pymorphy3
import language_tool_python
import hashlib
import json
import re
import string
from threading import Lock

from .template_blacklist import contains_blacklist
from .text_cache import TextCache
from .metrics_tracker import MetricsTracker
from .metrics_utils import compute_bleu, compute_rouge
from .generation_types import GenerateRequest, GenerateResult
from .template_model import Template


class BirthdayGenerator:
    _shared_lock = Lock()
    _shared_morph = None
    _shared_tool = None
    _shared_cache = None
    _shared_metrics = None

    def __init__(self):
        self.morph = self._get_shared_morph()
        self.tool = self._get_shared_tool()
        self.cache = self._get_shared_cache()
        self.metrics = self._get_shared_metrics()
        self._closed = False

    @classmethod
    def _get_shared_morph(cls):
        if cls._shared_morph is None:
            with cls._shared_lock:
                if cls._shared_morph is None:
                    cls._shared_morph = pymorphy3.MorphAnalyzer()
        return cls._shared_morph

    @classmethod
    def _get_shared_tool(cls):
        if cls._shared_tool is None:
            with cls._shared_lock:
                if cls._shared_tool is None:
                    cls._shared_tool = language_tool_python.LanguageTool("ru")
        return cls._shared_tool

    @classmethod
    def _get_shared_cache(cls):
        if cls._shared_cache is None:
            with cls._shared_lock:
                if cls._shared_cache is None:
                    cls._shared_cache = TextCache()
        return cls._shared_cache

    @classmethod
    def _get_shared_metrics(cls):
        if cls._shared_metrics is None:
            with cls._shared_lock:
                if cls._shared_metrics is None:
                    cls._shared_metrics = MetricsTracker()
        return cls._shared_metrics

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.tool = None
        self.morph = None
        self.cache = None
        self.metrics = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _mask_placeholders_for_grammar(self, text: str, values_to_protect: list[str]) -> tuple[str, dict[str, str]]:
        token_map: dict[str, str] = {}
        temp = text
        for i, val in enumerate(sorted(set(values_to_protect), key=len, reverse=True)):
            if not val:
                continue
            token = f"__TW_TOKEN_{i}__"
            token_map[token] = val
            temp = temp.replace(val, token)
        return temp, token_map

    def check_grammar(self, text: str, protected_values: list[str] | None = None):
        protected_values = protected_values or []
        masked, token_map = self._mask_placeholders_for_grammar(text, protected_values)

        matches = self.tool.check(masked)
        corrected = language_tool_python.utils.correct(masked, matches)

        for token, real in token_map.items():
            corrected = corrected.replace(token, real)

        # Если grammar tool вернул текст с неразрешёнными защитными токенами,
        # лучше отдать исходный вариант, чем сломанное поздравление.
        if "__TW_TOKEN_" in corrected:
            corrected = text

        words = max(1, len(corrected.split()))
        grammar_score = max(0.0, 1.0 - (len(matches) / words))
        return corrected, matches, round(grammar_score, 4)

    def get_name_case(self, name: str, case: str = "nomn") -> str:
        try:
            parsed = self.morph.parse(name)[0]
            inflected = parsed.inflect({case})
            return inflected.word.capitalize() if inflected else name
        except Exception:
            return name

    def pick_wish_deterministic(self, contact_id: int, template_id: int, wishes: list[str]) -> str:
        if not wishes:
            return ""
        raw = f"{contact_id}:{template_id}".encode("utf-8")
        idx = int(hashlib.md5(raw).hexdigest(), 16) % len(wishes)
        return wishes[idx]

    @staticmethod
    def _tone_hint(style: str) -> str:
        mapping = {
            "business": "деловой",
            "official": "официальный",
            "friendly": "дружеский",
        }
        return mapping.get((style or "").lower(), style or "")

    @staticmethod
    def _safe_str(value) -> str:
        if value is None:
            return ""
        return str(value)

    def _build_placeholders(
        self,
        *,
        template: Template,
        req: GenerateRequest,
        case: str,
        name_in_case: str,
        wish_phrase: str,
    ) -> dict[str, str]:
        first_name = (req.first_name or req.name or "").strip()
        last_name = (req.last_name or "").strip()
        middle_name = (req.middle_name or "").strip()
        full_name = (req.full_name or " ".join(part for part in [last_name, first_name, middle_name] if part)).strip()

        signature = (req.signature or f"Команда {req.company}".strip()).strip() if req.company else (req.signature or "").strip()

        return {
            "id": self._safe_str(req.contact_id),
            "contact_id": self._safe_str(req.contact_id),
            "name": first_name,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "full_name": full_name,
            "gender": self._safe_str(req.gender),
            "birthday": req.birthday.isoformat() if req.birthday else "",
            "age": self._safe_str(req.age),
            "position": self._safe_str(req.position),
            "company": self._safe_str(req.company),
            "tz": self._safe_str(req.tz),
            "tg_username": self._safe_str(req.tg_username),
            "email": self._safe_str(req.email),
            "preferred_channel": self._safe_str(req.preferred_channel),
            "default_style": self._safe_str(req.default_style),
            "segment": self._safe_str(req.segment),
            "notes": self._safe_str(req.notes),
            "tg_chat_id": self._safe_str(req.tg_chat_id),
            "is_active": self._safe_str(req.is_active),
            "is_deleted": self._safe_str(req.is_deleted),
            "created_at": self._safe_str(req.created_at),
            "updated_at": self._safe_str(req.updated_at),
            "channel": self._safe_str(req.channel),
            "style": self._safe_str(req.style),
            "tone": self._tone_hint(req.style),
            "holiday": self._safe_str(req.holiday_name),
            "holiday_name": self._safe_str(req.holiday_name),
            "signature": signature,
            "wish_phrase": wish_phrase,
            "wish": wish_phrase,
            "name_wish": name_in_case if case == "accs" else first_name,
            "name_accs": self.get_name_case(first_name, "accs") or first_name,
            "name_datv": self.get_name_case(first_name, "datv") or first_name,
            "name_gen": self.get_name_case(first_name, "gent") or first_name,
            "name_nomn": self.get_name_case(first_name, "nomn") or first_name,
            "template_id": self._safe_str(template.id),
            "template_version": self._safe_str(template.version),
        }

    @staticmethod
    def _format_template(body_text: str, placeholders: dict[str, str]) -> str:
        formatter = string.Formatter()
        parts: list[str] = []
        for literal_text, field_name, format_spec, conversion in formatter.parse(body_text):
            parts.append(literal_text)
            if field_name is None:
                continue
            value = placeholders.get(field_name, "")
            if conversion:
                value = formatter.convert_field(value, conversion)
            if format_spec:
                value = formatter.format_field(value, format_spec)
            parts.append(str(value))
        return "".join(parts)

    @staticmethod
    def _has_unresolved_placeholders(text: str) -> bool:
        return bool(re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", text or ""))

    async def render(self, template: Template, req: GenerateRequest) -> GenerateResult:
        wishes = req.wishes or ["счастья", "здоровья", "успехов"]

        CASE_MAP = {
            "Nominative": "nomn",
            "Genitive": "gent",
            "Dative": "datv",
            "Accusative": "accs",
            "Instrumental": "ablt",
            "Prepositional": "loct",
        }

        case = CASE_MAP.get(template.case, "nomn")
        if not case:
            t = template.body_text
            if "{name_wish}" in t or "{name_accs}" in t:
                case = "accs"
            elif "{name_datv}" in t:
                case = "datv"
            elif "{name_gen}" in t:
                case = "gent"
            else:
                case = "nomn"

        name_in_case = self.get_name_case(req.name, case)
        wish_phrase = self.pick_wish_deterministic(req.contact_id, template.id, wishes)

        placeholders = self._build_placeholders(
            template=template,
            req=req,
            case=case,
            name_in_case=name_in_case,
            wish_phrase=wish_phrase,
        )
        context_key = hashlib.md5(
            json.dumps(placeholders, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        cached = await self.cache.get(
            engine="template",
            contact_id=req.contact_id,
            holiday_id=req.holiday_id,
            style=req.style,
            template_id=template.id,
            template_version=template.version,
            name=req.name,
            wish_phrase=wish_phrase,
            context_key=context_key,
        )
        if cached:
            self.metrics.update(template_id=template.id, text=cached, contact_id=req.contact_id, version=template.version)
            return GenerateResult(
                template_id=template.id,
                contact_id=req.contact_id,
                rendered_text=cached,
                grammar_score=None,
                cache_hit=True,
                bleu=None,
                rouge=None,
                meta={"engine": "template", "template_version": template.version, "case": case},
            )

        text = self._format_template(template.body_text, placeholders)
        if self._has_unresolved_placeholders(text):
            raise ValueError(f"Template {template.id} contains unresolved placeholders after rendering")

        bad = contains_blacklist(text)
        if bad:
            raise ValueError(f"Запрещённое слово: '{bad}'. Нужна переформулировка.")

        protected_values = [value for value in placeholders.values() if value]
        corrected_text, matches, grammar_score = self.check_grammar(text, protected_values=protected_values)

        bleu = compute_bleu(template.body_text, corrected_text)
        rouge = compute_rouge(template.body_text, corrected_text)

        self.metrics.update(
            template_id=template.id,
            text=corrected_text,
            contact_id=req.contact_id,
            version=template.version,
            bleu=bleu,
            rouge=rouge,
        )

        await self.cache.set(
            engine="template",
            text_value=corrected_text,
            contact_id=req.contact_id,
            holiday_id=req.holiday_id,
            style=req.style,
            template_id=template.id,
            template_version=template.version,
            name=req.name,
            wish_phrase=wish_phrase,
            context_key=context_key,
        )

        return GenerateResult(
            template_id=template.id,
            contact_id=req.contact_id,
            rendered_text=corrected_text,
            grammar_score=grammar_score,
            cache_hit=False,
            bleu=bleu,
            rouge=rouge,
            meta={
                "engine": "template",
                "template_version": template.version,
                "case": case,
                "grammar_errors": len(matches),
            },
        )
