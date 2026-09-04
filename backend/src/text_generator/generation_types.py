from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class GenerateRequest:
    contact_id: int
    name: str
    style: str
    channel: str = "telegram"
    holiday_id: str = "birthday"
    holiday_name: str = "днём рождения"
    wishes: Optional[list[str]] = None
    signature: Optional[str] = None
    full_name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    position: Optional[str] = None
    company: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    birthday: Optional[date] = None
    tz: Optional[str] = None
    tg_username: Optional[str] = None
    email: Optional[str] = None
    preferred_channel: Optional[str] = None
    default_style: Optional[str] = None
    segment: Optional[str] = None
    notes: Optional[str] = None
    tg_chat_id: Optional[str] = None
    is_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class GenerateResult:
    template_id: int
    contact_id: int
    rendered_text: str
    grammar_score: Optional[float] = None  # 0..1 (или %)
    cache_hit: bool = False
    bleu: Optional[float] = None
    rouge: Optional[Dict[str, float]] = None
    meta: Optional[Dict[str, Any]] = None
