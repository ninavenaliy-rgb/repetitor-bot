"""Subscription access control middleware."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from loguru import logger

from src.database.engine import get_session
from src.services.subscription_service import SubscriptionService

# Single shared instance — avoids re-creating service object on every request
_subscription_service = SubscriptionService()


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware to check subscription status and feature access."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        """Check subscription before executing handler."""
        # Always provide default values so handlers don't crash
        data["subscription"] = None
        data["subscription_plan"] = None

        # Skip subscription lookup if not a tutor
        db_tutor = data.get("db_tutor")
        if not db_tutor:
            return await handler(event, data)

        # Get subscription info
        try:
            subscription, plan = await _subscription_service.get_subscription_with_plan(db_tutor.id)
        except Exception as e:
            logger.error(f"Failed to load subscription for tutor {db_tutor.id}: {e}")
            return await handler(event, data)  # proceed without subscription data

        # Inject into handler context
        data["subscription"] = subscription
        data["subscription_plan"] = plan

        # Check if subscription is active
        if not subscription or not subscription.is_active:
            # Block access to premium features
            if await self._is_premium_handler(handler):
                await self._send_subscription_required(event)
                return

        # Add helper functions to context
        data["has_feature"] = lambda feature_key: (
            plan.has_feature(feature_key) if plan else False
        )
        data["check_limit"] = lambda limit_key: self._check_limit(
            subscription, plan, limit_key, data
        )

        return await handler(event, data)

    async def _is_premium_handler(self, handler: Callable) -> bool:
        """Check if handler requires premium subscription."""
        # Check if handler is decorated with @requires_feature
        if hasattr(handler, "_requires_feature"):
            return True

        # Check handler name patterns
        # Handle functools.partial and other wrapper objects
        if hasattr(handler, '__name__'):
            handler_name = handler.__name__
        elif hasattr(handler, 'func') and hasattr(handler.func, '__name__'):
            handler_name = handler.func.__name__
        else:
            return False  # Can't determine handler name, assume not premium

        premium_patterns = [
            "lesson_plan",  # AI lesson planning
            "voice_homework",  # Voice homework
            "analytics_detail",  # Detailed analytics
            "calendar_sync",  # Google Calendar sync
        ]

        return any(pattern in handler_name for pattern in premium_patterns)

    async def _send_subscription_required(self, event: Message | CallbackQuery):
        """Send subscription upgrade message."""
        text = (
            "🔒 <b>Требуется подписка</b>\n\n"
            "Эта функция доступна на платных тарифах.\n\n"
            "📊 <b>Доступные тарифы:</b>\n"
            "• СТАРТ (990₽/мес) — всё необходимое для работы\n"
            "• ПРО (1 990₽/мес) — AI без лимитов + расширенная аналитика\n\n"
            "💎 Попробуйте бесплатно 7 дней!"
        )

        if isinstance(event, Message):
            await event.answer(text, parse_mode="HTML")
        else:
            await event.message.answer(text, parse_mode="HTML")
            await event.answer()

    def _check_limit(
        self, subscription, plan, limit_key: str, data: Dict[str, Any]
    ) -> bool:
        """Check if user is within usage limits."""
        if not subscription or not plan:
            return False

        if limit_key == "students":
            current_count = data.get("students_count", 0)
            return current_count < plan.max_students

        elif limit_key == "ai_checks":
            # Check monthly AI usage
            if not plan.has_feature("ai_homework_check"):
                return False
            # Could check usage_tracking here for monthly limits
            return True

        elif limit_key == "calendar_sync":
            return plan.has_feature("calendar_sync")

        return False


def requires_feature(feature_key: str):
    """Decorator to mark handlers that require specific features.

    Usage:
        @requires_feature("ai_homework_check")
        async def voice_homework_handler(message, db_tutor, has_feature):
            # Will only execute if subscription has this feature
            pass
    """

    def decorator(handler: Callable):
        async def wrapper(
            event: Message | CallbackQuery, *args, **kwargs
        ) -> Any:
            data = kwargs
            plan = data.get("subscription_plan")

            if not plan or not plan.has_feature(feature_key):
                await _send_feature_required(event, feature_key)
                return

            return await handler(event, *args, **kwargs)

        wrapper._requires_feature = feature_key  # Mark for middleware
        return wrapper

    return decorator


async def _send_feature_required(event: Message | CallbackQuery, feature_key: str):
    """Send message about missing feature."""
    feature_names = {
        "ai_homework_check": "AI проверка домашних заданий",
        "calendar_sync": "Синхронизация с Google Calendar",
        "analytics_detail": "Детальная аналитика",
        "parent_notifications": "Уведомления родителям",
        "voice_homework": "Голосовые домашние задания",
    }

    feature_name = feature_names.get(feature_key, "эта функция")

    text = (
        f"🔒 <b>Недоступно</b>\n\n"
        f"{feature_name.capitalize()} доступна на тарифе ПРО (1 990₽/мес).\n\n"
        f"Перейти в /subscription для апгрейда."
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML")
    else:
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()


class StudentLimitMiddleware(BaseMiddleware):
    """Middleware to check student limits before adding new students."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        """Check student limit before adding."""
        # Only check on student registration/invite handlers
        handler_name = (
            getattr(handler, "__name__", None)
            or getattr(getattr(handler, "func", None), "__name__", "")
        )
        if "student" not in handler_name and "invite" not in handler_name:
            return await handler(event, data)

        db_tutor = data.get("db_tutor")
        if not db_tutor:
            return await handler(event, data)

        # Get current student count
        async with get_session() as session:
            from src.database.repositories.user_repo import UserRepository

            user_repo = UserRepository(session)
            students = await user_repo.get_active_by_tutor(db_tutor.id)
            current_count = len(students)

        # Check limit
        service = SubscriptionService()
        within_limit = await service.check_student_limit(db_tutor.id, current_count)

        if not within_limit:
            subscription, plan = await service.get_subscription_with_plan(db_tutor.id)
            max_students = plan.max_students if plan else 5

            text = (
                f"⚠️ <b>Достигнут лимит учеников</b>\n\n"
                f"На вашем тарифе максимум {max_students} учеников.\n"
                f"Сейчас у вас: {current_count}\n\n"
                f"Обновите подписку в /subscription для увеличения лимита."
            )

            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML")
            else:
                await event.message.answer(text, parse_mode="HTML")
                await event.answer()

            return

        # Add count to context
        data["students_count"] = current_count
        return await handler(event, data)
