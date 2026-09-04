import asyncio

from .db import SessionMaker
from .db_template_loader import DBTemplateLoader
from .birthday_generator import BirthdayGenerator
from .generation_types import GenerateRequest


async def try_llm_stub(req: GenerateRequest) -> str:
    # Заглушка: имитируем, что DeepSeek недоступен/упал
    raise RuntimeError("DeepSeek is not configured yet")


async def main():
    async with SessionMaker() as session:
        loader = DBTemplateLoader(session)

        req = GenerateRequest(
            contact_id=1,
            name="Маргарита",
            style="business",
            channel="telegram",
            holiday_id="birthday",
            holiday_name="днём рождения",
            wishes=["счастья", "здоровья", "успехов"],
        )

        # 1) Пробуем LLM (пока заглушка)
        try:
            text = await try_llm_stub(req)
            print("✅ LLM text:", text)
            return
        except Exception as e:
            print("⚠️ LLM failed, fallback to templates:", e)

        # 2) Fallback: шаблон из БД → твой генератор
        template = await loader.get_template(
            style=req.style,
            channel=req.channel,
            category=req.holiday_id,
            language="ru",
        )
        if not template:
            raise RuntimeError("Не найден шаблон в БД под заданные фильтры")

        generator = BirthdayGenerator()
        res = await generator.render(template, req)

        print("✅ TEMPLATE text:", res.rendered_text)
        print("template_id:", res.template_id, "cache_hit:", res.cache_hit, "grammar:", res.grammar_score)


if __name__ == "__main__":
    asyncio.run(main())
