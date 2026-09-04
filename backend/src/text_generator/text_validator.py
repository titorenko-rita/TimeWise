import re
from .template_blacklist import contains_blacklist

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")

STYLE_LIMITS = {
    "friendly": 250,
    "business": 400,
    "official": 500,
}

def validate_generated_text(
    text: str,
    style: str,
    blacklist_phrases: list[str] | None = None,
) -> tuple[bool, str | None]:
    t = (text or "").strip()
    if not t:
        return False, "empty"

    limit = STYLE_LIMITS.get(style, 400)
    if len(t) > limit:
        return False, f"too_long>{limit}"

    bad = contains_blacklist(t, blacklist_phrases)
    if bad:
        return False, f"blacklist:{bad}"

    if style in ("business", "official") and EMOJI_RE.search(t):
        return False, "emoji_forbidden"

    return True, None


def validate_llm_text(text: str, style: str) -> tuple[bool, str | None]:
    return validate_generated_text(text, style)
