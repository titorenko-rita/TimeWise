from __future__ import annotations

import html
import os
import re
from io import BytesIO

import pymorphy3
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


_FONT_FAMILY = "Helvetica"
_FONT_FAMILY_BOLD = "Helvetica-Bold"
_FONT_REGISTERED = False
_MORPH = None


def _get_morph():
    global _MORPH
    if _MORPH is None:
        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def _register_pdf_fonts() -> None:
    global _FONT_FAMILY, _FONT_FAMILY_BOLD, _FONT_REGISTERED

    if _FONT_REGISTERED:
        return

    regular_font = r"C:\Windows\Fonts\arial.ttf"
    bold_font = r"C:\Windows\Fonts\arialbd.ttf"

    if os.path.exists(regular_font) and os.path.exists(bold_font):
        pdfmetrics.registerFont(TTFont("TimeWiseArial", regular_font))
        pdfmetrics.registerFont(TTFont("TimeWiseArialBold", bold_font))
        _FONT_FAMILY = "TimeWiseArial"
        _FONT_FAMILY_BOLD = "TimeWiseArialBold"

    _FONT_REGISTERED = True


def _restore_capitalization(source: str, inflected: str) -> str:
    if not inflected:
        return source
    if source.isupper():
        return inflected.upper()
    if source[:1].isupper():
        return inflected[:1].upper() + inflected[1:]
    return inflected


def _fallback_inflect_surname(value: str, case: str) -> str:
    lower = value.lower()
    unchanged_suffixes = ("ко", "енко", "их", "ых", "ово", "аго", "иа", "уа")
    if lower.endswith(unchanged_suffixes):
        return value

    if case == "gent":
        if lower.endswith(("ов", "ев", "ёв", "ин", "ын")):
            return value + "а"
        if lower.endswith(("ский", "цкий", "ской")):
            return value[:-2] + "ого"
    if case == "datv":
        if lower.endswith(("ов", "ев", "ёв", "ин", "ын")):
            return value + "у"
        if lower.endswith(("ский", "цкий", "ской")):
            return value[:-2] + "ому"
    return value


def _inflect_person_part(value: str, case: str, grammeme: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or case == "nomn":
        return cleaned

    if grammeme == "Surn" and cleaned.lower().endswith(("ов", "ев", "ёв", "ин", "ын", "ский", "цкий", "ской")):
        return _fallback_inflect_surname(cleaned, case)

    morph = _get_morph()
    best = None
    for parsed in morph.parse(cleaned):
        if grammeme in parsed.tag:
            best = parsed
            break
        if best is None:
            best = parsed

    if best is None:
        return cleaned

    inflected = best.inflect({case})
    if inflected is None:
        if grammeme == "Surn":
            return _fallback_inflect_surname(cleaned, case)
        return cleaned

    result = _restore_capitalization(cleaned, inflected.word)
    if grammeme == "Surn" and result == cleaned and case != "nomn":
        return _fallback_inflect_surname(cleaned, case)
    return result


def build_full_name(payload: dict, case: str = "nomn") -> str:
    parts = [
        _inflect_person_part(payload.get("last_name") or "", case, "Surn"),
        _inflect_person_part(payload.get("first_name") or "", case, "Name"),
        _inflect_person_part(payload.get("middle_name") or "", case, "Patr"),
    ]
    full_name = " ".join(part for part in parts if part)
    return full_name or str(payload.get("first_name") or "Получатель")


def _build_greeting_name(payload: dict) -> str:
    first_name = str(payload.get("first_name") or "").strip()
    if first_name:
        return first_name
    return build_full_name(payload)


def build_email_text(payload: dict) -> str:
    greeting_name = _build_greeting_name(payload)
    rendered_text = str(payload.get("rendered_text") or "").strip()
    return (
        f"Здравствуйте, {greeting_name}!\n\n"
        f"{rendered_text}\n\n"
        "С уважением,\n"
        "Команда TimeWise"
    )


def build_email_html(payload: dict) -> str:
    greeting_name = html.escape(_build_greeting_name(payload))
    rendered_text = html.escape(str(payload.get("rendered_text") or "").strip()).replace("\n", "<br>")
    event_date = html.escape(str(payload.get("event_date") or ""))

    meta_block = ""
    if event_date:
        meta_block = f'<p style="margin:0 0 16px;color:#6b7280;font-size:13px;">Дата события: {event_date}</p>'

    return f"""\
<!doctype html>
<html lang="ru">
  <body style="margin:0;padding:24px;background:#f3f4f6;font-family:Segoe UI,Arial,sans-serif;color:#111827;">
    <div style="max-width:680px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8);padding:24px 28px;color:#ffffff;">
        <div style="display:inline-block;padding:6px 10px;border:1px solid rgba(255,255,255,0.45);border-radius:999px;font-size:12px;letter-spacing:0.08em;">
          TIMEWISE
        </div>
        <h1 style="margin:16px 0 6px;font-size:26px;line-height:1.2;">Поздравление</h1>
        <p style="margin:0;font-size:14px;opacity:0.9;">HTML-письмо с PDF-вложением</p>
      </div>
      <div style="padding:28px;">
        <p style="margin:0 0 12px;font-size:18px;font-weight:600;">Здравствуйте, {greeting_name}!</p>
        {meta_block}
        <div style="font-size:16px;line-height:1.7;color:#1f2937;">{rendered_text}</div>
      </div>
      <div style="padding:20px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;color:#6b7280;font-size:13px;">
        С уважением,<br>Команда TimeWise
      </div>
    </div>
  </body>
</html>
"""


def _pdf_styles():
    _register_pdf_fonts()
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TimeWiseTitle",
            parent=sample["Title"],
            fontName=_FONT_FAMILY_BOLD,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "body": ParagraphStyle(
            "TimeWiseBody",
            parent=sample["BodyText"],
            fontName=_FONT_FAMILY,
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "TimeWiseMeta",
            parent=sample["BodyText"],
            fontName=_FONT_FAMILY,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=10,
        ),
        "footer": ParagraphStyle(
            "TimeWiseFooter",
            parent=sample["BodyText"],
            fontName=_FONT_FAMILY,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#4b5563"),
            spaceBefore=16,
        ),
    }


def _sanitize_pdf_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[\U00010000-\U0010ffff]", "", value)
    return value


def _build_pdf_filename(payload: dict) -> str:
    event_id = str(payload.get("event_id") or "event")
    return f"timewise-greeting-{event_id}.pdf"


def build_email_pdf_bytes(payload: dict) -> tuple[str, bytes]:
    styles = _pdf_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="TimeWise greeting",
    )

    event_date = html.escape(str(payload.get("event_date") or ""))
    full_name = html.escape(build_full_name(payload, case="datv"))
    body_text = _sanitize_pdf_text(str(payload.get("rendered_text") or "").strip())

    story = []
    logo_table = Table(
        [["TIMEWISE"]],
        colWidths=[70 * mm],
    )
    logo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1d4ed8")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, -1), _FONT_FAMILY_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("ROUNDEDCORNERS", [10, 10, 10, 10]),
            ]
        )
    )

    story.append(logo_table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Поздравление", styles["title"]))
    story.append(Paragraph(f"Получатель: {full_name}", styles["meta"]))
    if event_date:
        story.append(Paragraph(f"Дата события: {event_date}", styles["meta"]))
    for line in body_text.split("\n"):
        if not line.strip():
            story.append(Spacer(1, 6))
            continue
        story.append(Paragraph(html.escape(line.strip()), styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("С уважением,<br/>Команда TimeWise", styles["footer"]))

    doc.build(story)
    return _build_pdf_filename(payload), buffer.getvalue()
