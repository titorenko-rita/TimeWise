from enum import Enum
from typing import Iterable


class UserRole(str, Enum):
    ADMIN = "Admin"
    EDITOR = "Editor"
    VIEWER = "Viewer"

    @classmethod
    def from_value(cls, raw: str | None) -> "UserRole | None":
        if not raw:
            return None
        normalized = raw.strip().lower()
        for r in cls:
            if r.value.lower() == normalized:
                return r
        return None


def resolve_role(user_id: int, admin_ids: Iterable[int]) -> UserRole:
    # Fallback, если БД ещё пуста/недоступна
    return UserRole.ADMIN if user_id in admin_ids else UserRole.VIEWER


