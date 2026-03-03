"""Logging middleware for all incoming updates."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from loguru import logger


class LoggingMiddleware(BaseMiddleware):
    """Log every incoming update with user info."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        user_id = user.id if user else "unknown"
        event_type = type(event).__name__
        logger.info(
            "Update received",
            extra={"user_id": user_id, "event_type": event_type},
        )
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(
                f"Handler error: {e}",
                extra={"user_id": user_id, "event_type": event_type},
            )
            raise
