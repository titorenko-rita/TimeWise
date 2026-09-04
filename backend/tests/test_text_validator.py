from src.text_generator.text_validator import validate_generated_text


def test_validate_generated_text_rejects_business_emoji():
    ok, reason = validate_generated_text("Здравствуйте! Успехов вам 🎉", "business")

    assert ok is False
    assert reason == "emoji_forbidden"


def test_validate_generated_text_rejects_too_long_friendly():
    ok, reason = validate_generated_text("а" * 251, "friendly")

    assert ok is False
    assert reason == "too_long>250"


def test_validate_generated_text_rejects_blacklist_phrase_from_db_list():
    ok, reason = validate_generated_text(
        "Поздравляем, ты дурак",
        "friendly",
        blacklist_phrases=["дурак"],
    )

    assert ok is False
    assert reason == "blacklist:дурак"


def test_validate_generated_text_accepts_valid_official_text():
    ok, reason = validate_generated_text(
        "Уважаемая Полина, примите искренние поздравления с днём рождения. Желаем благополучия и успехов.",
        "official",
        blacklist_phrases=["дурак"],
    )

    assert ok is True
    assert reason is None
