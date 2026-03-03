"""Authentication middleware — loads or creates user from DB."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.database.engine import get_session
from src.database.repositories.tutor_repo import TutorRepository
from src.database.repositories.user_repo import UserRepository


class AuthMiddleware(BaseMiddleware):
    """Load user and tutor from DB and inject into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        async with get_session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(tg_user.id)

            if not user:
                user = await repo.create(
                    telegram_id=tg_user.id,
                    name=tg_user.full_name or "",
                )

            tutor_repo = TutorRepository(session)
            tutor = await tutor_repo.get_by_telegram_id(tg_user.id)
        # Session committed and closed BEFORE handler runs —
        # prevents SQLite lock contention when handler opens its own session.

        data["db_user"] = user
        data["db_tutor"] = tutor
        return await handler(event, data)
