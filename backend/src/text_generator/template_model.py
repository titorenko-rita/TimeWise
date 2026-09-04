from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Template:
    id: int
    channel: str          # "telegram" | "email"
    style: str            # "friendly" | "business" | "official"
    category: str         # "birthday" | "professional" | "corporate" ...
    language: str = "ru"
    body_text: str = ""
    version: int = 1
    case: Optional[str] = None  # 'nomn', 'datv', 'accs', 'gent'
    target_gender: Optional[str] = None  # 'Male' | 'Female' | None
    is_active: bool = True
