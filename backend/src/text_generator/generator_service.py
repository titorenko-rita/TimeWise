from .generation_types import GenerateRequest, GenerateResult  # :contentReference[oaicite:9]{index=9}
from .text_cache import TextCache  # твой класс
from .db_template_loader import DBTemplateLoader
from .birthday_generator import BirthdayGenerator
from .text_validator import validate_llm_text
from .llm_provider import DeepSeekProvider


class GeneratorService:
    def __init__(self, session, llm: DeepSeekProvider | None = None, cache: TextCache | None = None):
        self.session = session
        self.loader = DBTemplateLoader(session)
        self.template_engine = BirthdayGenerator()
        self.llm = llm
        self.cache = cache or TextCache()

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        # 1) Для кэша template_id/version пока неизвестны — делаем “условные”
        # чтобы хотя бы работало. Лучше: кэшировать отдельно для llm и template.
        cache_kwargs = dict(
            contact_id=req.contact_id,
            holiday_id=req.holiday_id,
            style=req.style,
            template_id=0,
            template_version=0,
            name=req.name,
            wish_phrase=",".join(req.wishes) if req.wishes else "",
        )
        cached = await self.cache.get(**cache_kwargs)
        if cached:
            return GenerateResult(
                template_id=0,
                contact_id=req.contact_id,
                rendered_text=cached,
                cache_hit=True,
                meta={"engine": "cache", "source": "llm_or_template"},
            )

        # 2) Пытаемся LLM (DeepSeek)
        if self.llm:
            try:
                llm_text = await self.llm.generate(req)
                ok, reason = validate_llm_text(llm_text, req.style)
                if ok:
                    # сохраняем в кэш
                    await self.cache.set(llm_text, **cache_kwargs)
                    return GenerateResult(
                        template_id=0,
                        contact_id=req.contact_id,
                        rendered_text=llm_text,
                        cache_hit=False,
                        meta={"engine": "llm", "model": "deepseek"},
                    )
            except Exception as e:
                # не падаем — просто идём в fallback
                llm_err = str(e)
            else:
                llm_err = reason
        else:
            llm_err = "llm_not_configured"

        # 3) Fallback на шаблоны из БД
        template = await self.loader.get_template(
            style=req.style,
            channel=req.channel,
            category=req.holiday_id,
            language="ru",
        )
        if not template:
            raise RuntimeError("Не найден шаблон в БД под заданные фильтры")

        res = await self.template_engine.render(template, req)
        res.meta = res.meta or {}
        res.meta.update({"fallback_from": "llm", "llm_error": llm_err})
        # кэшируем уже как template
        await self.cache.set(res.rendered_text, **cache_kwargs)
        return res
