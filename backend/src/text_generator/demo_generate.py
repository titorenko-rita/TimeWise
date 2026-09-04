import asyncio

from src.text_generator import BirthdayGenerator, GenerateRequest
from src.text_generator.db import SessionMaker
from src.text_generator.db_template_loader import DBTemplateLoader


async def main():
    async with SessionMaker() as session:
        loader = DBTemplateLoader(session)
        gen = BirthdayGenerator()
        req = GenerateRequest(
            contact_id=1,
            name="Маргарита",
            style="business",
            channel="telegram",
            holiday_id="birthday",
            holiday_name="днём рождения",
            wishes=["счастья", "здоровья", "успехов"],
        )

        template = await loader.get_template(
            style=req.style,
            channel=req.channel,
            category=req.holiday_id,
            language="ru",
        )
        if not template:
            raise RuntimeError("Не найден шаблон в БД под заданные фильтры")

        res1 = await gen.render(template, req)
        print(res1.rendered_text)
        print("cache_hit:", res1.cache_hit, "grammar:", res1.grammar_score)

        res2 = await gen.render(template, req)
        print(res2.rendered_text)
        print("cache_hit:", res2.cache_hit, "grammar:", res2.grammar_score)


if __name__ == "__main__":
    asyncio.run(main())
