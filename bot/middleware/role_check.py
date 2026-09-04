"""Middleware для проверки ролей и добавления роли в контекст."""

import logging
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from db.repositories.users import get_by_tg_id
from db.session import get_sessionmaker
from roles import UserRole, resolve_role

logger = logging.getLogger(__name__)
ROLE_CACHE_TTL_SEC = 120.0


class RoleCheckMiddleware(BaseMiddleware):
    """
    Добавляет роль пользователя в data["role"].
    Блокирует admin-действия для обычных пользователей.
    """

    def __init__(self, admin_ids: List[int]) -> None:
        self.admin_ids = admin_ids
        self._sessionmaker = get_sessionmaker()
        self._identity_cache: dict[int, tuple[float, UserRole, int | None]] = {}

    async def _get_identity(self, tg_id: int) -> tuple[UserRole, int | None]:
        cached = self._identity_cache.get(tg_id)
        now = monotonic()
        if cached and cached[0] > now:
            return cached[1], cached[2]

        role: UserRole | None = None
        actor_user_id: int | None = None
        try:
            async with self._sessionmaker() as session:
                db_user = await get_by_tg_id(session, tg_id)
            if db_user and db_user.is_active:
                actor_user_id = db_user.id
                role = UserRole.from_value(db_user.role)
        except Exception as e:
            logger.warning("Не удалось получить роль из БД для user_id=%d: %s", tg_id, e)

        if role is None:
            role = resolve_role(tg_id, self.admin_ids)

        self._identity_cache[tg_id] = (now + ROLE_CACHE_TTL_SEC, role, actor_user_id)
        return role, actor_user_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        role, actor_user_id = await self._get_identity(user.id)

        data["role"] = role
        data["actor_user_id"] = actor_user_id

        # Проверка доступа к функциям по ролям (RBAC)
        if isinstance(event, CallbackQuery) and event.data:
            d = event.data

            # Любые admin:* по умолчанию только для Admin,
            # кроме явно разрешённых разделов для Editor.
            if d.startswith("admin:") and role != UserRole.ADMIN:
                if role == UserRole.EDITOR and d in {"admin:contacts", "admin:templates", "admin:approvals", "admin:blacklist"}:
                    pass
                else:
                    await event.answer("⛔ Доступ запрещён. Только Admin.", show_alert=True)
                    return None

            # Admin-only блок (пользователи/настройки/мониторинг/рассылки)
            if d in {"admin:users", "admin:settings", "admin:monitoring", "admin:campaigns"}:
                if role != UserRole.ADMIN:
                    await event.answer("⛔ Доступ запрещён. Только Admin.", show_alert=True)
                    return None

            # Editor allowed (контакты/шаблоны/approval/черный список)
            if d in {"admin:contacts", "admin:templates", "admin:approvals", "admin:blacklist"}:
                if role not in {UserRole.ADMIN, UserRole.EDITOR}:
                    await event.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
                    return None

            # Viewer-only разделы
            if d.startswith("viewer:") and role != UserRole.VIEWER:
                await event.answer("⛔ Доступ запрещён. Только Viewer.", show_alert=True)
                return None

            # Контакты: любые действия только Admin/Editor
            if d.startswith("contacts:") and role not in {UserRole.ADMIN, UserRole.EDITOR}:
                await event.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
                return None

            # Черный список: любые действия только Admin/Editor
            if d.startswith("blacklist:") and role not in {UserRole.ADMIN, UserRole.EDITOR}:
                await event.answer("⛔ Доступ запрещён. Только Admin/Editor.", show_alert=True)
                return None

            # Контакты: удаление только Admin (включая подтверждение)
            if d in {"contacts:delete"} or d.startswith("contacts:delete_confirm:"):
                if role != UserRole.ADMIN:
                    await event.answer("⛔ Удаление доступно только Admin.", show_alert=True)
                    return None

        return await handler(event, data)
