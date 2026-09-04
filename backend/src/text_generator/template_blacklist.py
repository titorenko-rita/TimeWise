import re
from sqlalchemy import text

DEFAULT_BLACKLIST = ["идиот", "дурак", "чертов", "блин", "паразит", "глупый"]


async def fetch_blacklist_phrases(session) -> list[str]:
    query = text(
        """
        SELECT phrase
        FROM public.template_blacklist
        WHERE is_deleted = false
          AND length(btrim(phrase)) > 0
        ORDER BY id ASC;
        """
    )
    result = await session.execute(query)
    phrases = []
    for row in result.fetchall():
        phrase = (row[0] or "").strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def contains_blacklist(text: str, phrases: list[str] | None = None):
    lower = text.lower()
    for w in phrases or DEFAULT_BLACKLIST:
        # границы слова на кириллице работают не идеально, но лучше чем "in"
        if re.search(rf"(^|[^а-яё]){re.escape(w)}([^а-яё]|$)", lower):
            return w
    return None
