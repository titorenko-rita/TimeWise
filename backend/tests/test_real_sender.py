import asyncio
import importlib
from pathlib import Path

from src.workflow.email_rendering import build_email_pdf_bytes, build_full_name
from src.workflow.real_sender import send_email

real_sender_module = importlib.import_module("src.workflow.real_sender")


class _FakeSMTP:
    last_message = None

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        return None

    def starttls(self):
        return None

    def login(self, username, password):
        self.username = username
        self.password = password

    def send_message(self, message):
        _FakeSMTP.last_message = message


def test_build_email_pdf_bytes_returns_pdf_bytes():
    filename, pdf_bytes = build_email_pdf_bytes(
        {
            "event_id": 123,
            "first_name": "Полина",
            "last_name": "Волкова",
            "middle_name": "Романовна",
            "event_date": "2026-05-02",
            "rendered_text": "Поздравляем с днём рождения!",
        }
    )

    assert filename == "timewise-greeting-123.pdf"
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_build_full_name_supports_russian_cases():
    payload = {
        "first_name": "Илья",
        "last_name": "Камаледдинов",
        "middle_name": "Андреевич",
    }

    assert build_full_name(payload) == "Камаледдинов Илья Андреевич"
    assert build_full_name(payload, case="gent") == "Камаледдинова Ильи Андреевича"
    assert build_full_name(payload, case="datv") == "Камаледдинову Илье Андреевичу"


def test_send_email_builds_html_and_pdf_attachment(monkeypatch):
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_SMTP_USER", "user")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "pass")
    monkeypatch.setenv("EMAIL_FROM", "timewise@example.com")
    monkeypatch.setenv("EMAIL_USE_STARTTLS", "1")
    monkeypatch.setenv("EMAIL_USE_SSL", "0")
    monkeypatch.setattr(real_sender_module.smtplib, "SMTP", _FakeSMTP)

    result = asyncio.run(
        send_email(
            {
                "event_id": 99,
                "event_date": "2026-05-02",
                "first_name": "Кирилл",
                "last_name": "Фёдоров",
                "middle_name": "Олегович",
                "email": "kirill@example.com",
                "rendered_text": "Кирилл, поздравляем Вас с днём рождения!",
            }
        )
    )

    assert result.status == "sent"
    assert _FakeSMTP.last_message is not None

    html_parts = [
        part
        for part in _FakeSMTP.last_message.walk()
        if part.get_content_type() == "text/html"
    ]
    pdf_parts = [
        part
        for part in _FakeSMTP.last_message.walk()
        if part.get_content_type() == "application/pdf"
    ]

    assert html_parts
    assert pdf_parts
    assert pdf_parts[0].get_filename() == "timewise-greeting-99.pdf"
    assert _FakeSMTP.last_message["Subject"] == "TimeWise: поздравление для Фёдорова Кирилла Олеговича (2026-05-02)"


def test_send_email_can_save_debug_eml(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_SMTP_USER", "user")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "pass")
    monkeypatch.setenv("EMAIL_FROM", "timewise@example.com")
    monkeypatch.setenv("EMAIL_USE_STARTTLS", "1")
    monkeypatch.setenv("EMAIL_USE_SSL", "0")
    monkeypatch.setenv("EMAIL_DEBUG_SAVE_DIR", str(tmp_path))
    monkeypatch.setattr(real_sender_module.smtplib, "SMTP", _FakeSMTP)

    result = asyncio.run(
        send_email(
            {
                "event_id": 100,
                "event_date": "2026-05-02",
                "first_name": "Полина",
                "last_name": "Волкова",
                "middle_name": "Романовна",
                "email": "polina@example.com",
                "rendered_text": "Полина, поздравляем Вас с днём рождения!",
            }
        )
    )

    assert result.status == "sent"
    eml_path = tmp_path / "timewise-email-100.eml"
    assert eml_path.exists()
    eml_bytes = eml_path.read_bytes()
    assert b"application/pdf" in eml_bytes
    assert b"timewise-greeting-100.pdf" in eml_bytes
