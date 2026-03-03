"""Middleware для проверки прав администратора."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from config.settings import settings


class AdminMiddleware(BaseMiddleware):
    """Проверяет, является ли пользователь администратором."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        """Проверка прав администратора."""
        user = event.from_user
        if not user:
            return

        admin_ids = settings.get_admin_ids()
        is_admin = user.id in admin_ids

        # Добавляем флаг в data
        data["is_admin"] = is_admin

        return await handler(event, data)
