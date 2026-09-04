import asyncio

from .db import SessionMaker
from .db_template_loader import DBTemplateLoader
from .birthday_generator import BirthdayGenerator
from .generation_types import GenerateRequest


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

        print(res.rendered_text)
        print("template_id:", res.template_id, "cache_hit:", res.cache_hit, "grammar:", res.grammar_score)


if __name__ == "__main__":
    asyncio.run(main())
