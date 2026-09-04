from __future__ import annotations

from dataclasses import dataclass

from .generation_types import GenerateRequest
from .llm_client import LLMClient


@dataclass
class LLMGeneratorResult:
    rendered_text: str
    used_model: str
    cache_hit: bool = False


class LLMGenerator:
    def __init__(self, client: LLMClient, model: str = "deepseek-chat") -> None:
        self.client = client
        self.model = model

    @staticmethod
    def _tone_hint(style: str) -> str:
        mapping = {
            "business": "деловой, тёплый и уважительный",
            "official": "официальный, сдержанный и корректный",
            "friendly": "живой, доброжелательный и более личный",
        }
        return mapping.get((style or "").lower(), "уважительный и естественный")

    @staticmethod
    def _gender_hint(gender: str | None) -> str:
        mapping = {
            "female": "женщина",
            "male": "мужчина",
        }
        return mapping.get((gender or "").lower(), "пол не указан")

    @staticmethod
    def _length_hint(style: str) -> int:
        mapping = {
            "friendly": 250,
            "business": 400,
            "official": 500,
        }
        return mapping.get((style or "").lower(), 400)

    def _build_messages(self, req: GenerateRequest) -> list[dict[str, str]]:
        tone_hint = self._tone_hint(req.style)
        gender_hint = self._gender_hint(req.gender)
        length_hint = self._length_hint(req.style)
        age_hint = f"{req.age} лет" if req.age is not None else "возраст не указан"
        position_hint = req.position or "должность не указана"
        company_hint = req.company or "компания не указана"
        wishes = ", ".join(req.wishes or [])

        system = (
            "Ты пишешь персонализированные поздравления на русском языке от имени команды или компании, "
            "поэтому используй форму множественного числа: например, 'поздравляем', 'желаем', 'ценим', "
            "а не 'поздравляю' или 'желаю'. "
            "Текст должен быть живым, небанальным и не выглядеть как копия одного и того же шаблона. "
            "Учитывай стиль, канал, пол, возраст, должность, компанию и сам повод. "
            "Не придумывай факты, которых нет во входных данных. "
            "Для business и official не используй эмодзи. "
            "Пиши 2-4 предложения, без списков и без кавычек."
        )

        user = (
            "Сгенерируй персонализированное поздравление по данным ниже.\n"
            f"Имя для обращения: {req.name}\n"
            f"Полное имя: {req.full_name or req.name}\n"
            f"Пол: {gender_hint}\n"
            f"Возраст: {age_hint}\n"
            f"Должность: {position_hint}\n"
            f"Компания: {company_hint}\n"
            f"Повод: {req.holiday_name}\n"
            f"Стиль: {req.style} ({tone_hint})\n"
            f"Канал: {req.channel}\n"
            f"Максимальная длина текста: {length_hint} символов\n"
            f"Пожелания и смысловые акценты: {wishes}\n"
            "Требования:\n"
            "- пиши от первого лица множественного числа, как от имени команды или компании;\n"
            "- сделай текст чуть более индивидуальным, а не универсальным;\n"
            "- уместно опирайся на профессию, роль человека или его вклад;\n"
            "- для дня рождения сделай поздравление теплее, но без лишней воды;\n"
            "- соблюдай ограничение по длине;\n"
            "- для business и official не используй эмодзи;\n"
            "- избегай повторов формулировок, которые подходят любому человеку без изменений;\n"
            "- не начинай каждый текст одинаково и не своди всё к одной и той же канцелярской формуле."
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def generate(self, req: GenerateRequest) -> LLMGeneratorResult:
        messages = self._build_messages(req)
        r = await self.client.chat_completions(
            model=self.model,
            messages=messages,
            temperature=0.85,
            max_tokens=320,
        )
        return LLMGeneratorResult(
            rendered_text=r.content,
            used_model=self.model,
            cache_hit=False,
        )
