from src.text_generator import BirthdayGenerator, GenerateRequest

generator = BirthdayGenerator()

contact_id = 1
name = "Маргарита"
style = "business"
wishes = ["счастья", "здоровья", "успехов"]

req = GenerateRequest(
    contact_id=contact_id,
    name=name,
    style=style,
    channel="telegram",       # базовый канал
    holiday_id="birthday",    # категория события
    holiday_name="днём рождения",
    wishes=wishes,
)

res = generator.generate(req)
print(res.rendered_text)
print("cache_hit:", res.cache_hit, "grammar:", res.grammar_score)
