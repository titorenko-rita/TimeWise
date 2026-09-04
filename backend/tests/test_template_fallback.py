import asyncio
from pathlib import Path
from types import SimpleNamespace

from src.text_generator.birthday_generator import BirthdayGenerator
from src.text_generator.db_template_loader import DBTemplateLoader
from src.text_generator.generation_types import GenerateRequest
from src.text_generator.template_model import Template
from src.text_generator.text_cache import TextCache


class DummyCache:
    def __init__(self):
        self.storage = {}

    async def get(self, **kwargs):
        return self.storage.get(tuple(sorted(kwargs.items())))

    async def set(self, text_value, **kwargs):
        self.storage[tuple(sorted(kwargs.items()))] = text_value


class DummyMetrics:
    def update(self, **kwargs):
        return None


def build_generator():
    generator = BirthdayGenerator.__new__(BirthdayGenerator)
    generator.cache = DummyCache()
    generator.metrics = DummyMetrics()
    generator.get_name_case = lambda name, case="nomn": f"{name}_{case}" if name else ""
    generator.pick_wish_deterministic = lambda contact_id, template_id, wishes: wishes[0] if wishes else ""
    generator.check_grammar = lambda text, protected_values=None: (text, [], 1.0)
    return generator


def test_template_fallback_renders_db_placeholders():
    generator = build_generator()
    template = Template(
        id=101,
        channel="email",
        style="official",
        category="birthday",
        language="ru",
        body_text=(
            "Уважаемая {first_name} {middle_name}! "
            "{position} в компании {company}, поздравляем {name_accs} с {holiday}. "
            "Канал: {preferred_channel}. Тон: {tone}. Подпись: {signature}."
        ),
        version=3,
        case="nomn",
    )
    req = GenerateRequest(
        contact_id=15,
        name="Полина",
        first_name="Полина",
        middle_name="Романовна",
        style="official",
        channel="telegram",
        holiday_id="birthday",
        holiday_name="днём рождения",
        position="Технический писатель",
        company="TimeWise",
        preferred_channel="Telegram",
    )

    result = asyncio.run(generator.render(template, req))

    assert "Полина Романовна" in result.rendered_text
    assert "Технический писатель" in result.rendered_text
    assert "TimeWise" in result.rendered_text
    assert "Полина_accs" in result.rendered_text
    assert "днём рождения" in result.rendered_text
    assert "Telegram" in result.rendered_text
    assert "официальный" in result.rendered_text
    assert "Команда TimeWise" in result.rendered_text


def test_text_cache_key_depends_on_placeholder_context(tmp_path: Path):
    cache = TextCache()

    common = dict(
        contact_id=15,
        holiday_id="birthday",
        style="official",
        template_id=101,
        template_version=3,
        name="Полина",
        wish_phrase="счастья",
        engine="template",
    )

    key_a = cache._make_key(context_key="company=TimeWise", **common)
    key_b = cache._make_key(context_key="company=Other", **common)

    assert key_a != key_b


def test_template_loader_prefers_gender_specific_latest_row():
    rows = [
        SimpleNamespace(id=1, body_text="neutral {first_name}", version=2, target_gender=None),
        SimpleNamespace(id=2, body_text="male {first_name} {middle_name}", version=2, target_gender="Male"),
        SimpleNamespace(id=3, body_text="female {first_name} {middle_name}", version=2, target_gender="Female"),
    ]

    picked = DBTemplateLoader._pick_row(rows, "Female", available_fields={"first_name", "middle_name"})

    assert picked.id == 3


def test_template_loader_falls_back_to_neutral_when_required_field_missing():
    rows = [
        SimpleNamespace(id=1, body_text="neutral {first_name}", version=2, target_gender=None),
        SimpleNamespace(id=2, body_text="gendered {first_name} {middle_name}", version=2, target_gender="Female"),
    ]

    picked = DBTemplateLoader._pick_row(rows, "Female", available_fields={"first_name"})

    assert picked.id == 1


def test_template_loader_uses_only_latest_version_pool():
    rows = [
        SimpleNamespace(id=1, body_text="old {first_name}", version=1, target_gender=None),
        SimpleNamespace(id=2, body_text="new a {first_name}", version=2, target_gender=None),
        SimpleNamespace(id=3, body_text="new b {first_name}", version=2, target_gender=None),
    ]

    picked = DBTemplateLoader._pick_row(rows, None, available_fields={"first_name"})

    assert picked.id in {2, 3}
