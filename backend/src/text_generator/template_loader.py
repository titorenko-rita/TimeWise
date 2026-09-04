import random
from typing import Optional
from .template_model import Template


class TemplateLoader:
    """
    Сейчас: шаблоны в памяти.
    Потом: будет SELECT из таблицы templates.
    Интерфейс уже "как под БД".
    """

    def __init__(self):
        self.templates = [
            # FRIENDLY / birthday / telegram
            Template(
                id=101, channel="telegram", style="friendly", category="birthday",
                language="ru", version=1, case="nomn",
                body_text="С днём рождения, {name_nomn}! Пусть {wish_phrase}."
            ),
            Template(
                id=102, channel="telegram", style="friendly", category="birthday",
                language="ru", version=1, case="nomn",
                body_text="Привет, {name}! Поздравляю тебя с {holiday}! Желаю {wish_phrase}."
            ),

            # BUSINESS / birthday / telegram
            Template(
                id=201, channel="telegram", style="business", category="birthday",
                language="ru", version=1, case="accs",
                body_text="Компания искренне поздравляет {name_wish} с {holiday} и желает {wish_phrase}."
            ),
            Template(
                id=202, channel="telegram", style="business", category="birthday",
                language="ru", version=1, case="datv",
                body_text="Дарим наши поздравления Вам, {name_datv}, с {holiday}! Желаем {wish_phrase}."
            ),

            # OFFICIAL / birthday / telegram
            Template(
                id=301, channel="telegram", style="official", category="birthday",
                language="ru", version=1, case="nomn",
                body_text="Уважаемая {name_nomn}, примите наши поздравления с {holiday}! Пусть {wish_phrase}."
            ),
            Template(
                id=302, channel="telegram", style="official", category="birthday",
                language="ru", version=1, case="nomn",
                body_text="{name_nomn}, поздравляем вас с {holiday} и желаем {wish_phrase}."
            ),
        ]

    def get_template(
        self,
        style: str,
        channel: str = "telegram",
        category: str = "birthday",
        language: str = "ru",
    ) -> Optional[Template]:
        candidates = [
            t for t in self.templates
            if t.is_active
            and t.style == style
            and t.channel == channel
            and t.category == category
            and t.language == language
        ]
        return random.choice(candidates) if candidates else None
