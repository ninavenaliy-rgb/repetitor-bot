"""Celery tasks for daily engagement content delivery."""

from __future__ import annotations

import asyncio

from loguru import logger

from src.celery_app.celery_config import celery_app
from src.celery_app.tasks.reminder_tasks import _send_telegram_message_sync


@celery_app.task(name="src.celery_app.tasks.engagement_tasks.send_daily_word")
def send_daily_word() -> dict:
    """Send Word of the Day to all active students."""

    async def _send():
        from sqlalchemy import and_, select

        from src.database.engine import get_session
        from src.database.models import User
        from src.services.engagement_service import EngagementService

        service = EngagementService()
        sent_count = 0

        async with get_session() as session:
            result = await session.execute(
                select(User).where(
                    and_(User.is_active == True, User.cefr_level.isnot(None))
                ).limit(5000)
            )
            users = list(result.scalars().all())

        for user in users:
            try:
                word = await service.get_word_of_day_ai(user.cefr_level or "B2")
                streak = await service.get_streak(user.id)
                text = service.format_word_of_day(word, streak)

                markup_data = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Составить предложение",
                                "callback_data": "engagement_use_word",
                            },
                        ],
                    ]
                }

                _send_telegram_message_sync(user.telegram_id, text, markup_data)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send WotD to {user.id}: {e}")

        return {"sent": sent_count, "total_users": len(users)}

    return asyncio.run(_send())


@celery_app.task(name="src.celery_app.tasks.engagement_tasks.check_streaks")
def check_streaks() -> dict:
    """Check for at-risk streaks and send nudge messages."""

    async def _check():
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import and_, select

        from src.database.engine import get_session
        from src.database.models import EngagementEvent, User
        from src.database.repositories.engagement_repo import EngagementRepository

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        nudged = 0

        async with get_session() as session:
            # Find users who had a streak yesterday but haven't engaged today
            result = await session.execute(
                select(User).where(User.is_active == True).limit(5000)
            )
            users = list(result.scalars().all())

            # Process all users within the same session to avoid session leaks
            repo = EngagementRepository(session)
            for user in users:
                today_event = await repo.get_today_event(user.id, "word_of_day")
                streak = await repo.get_current_streak(user.id)

                if streak > 2 and not today_event:
                    text = (
                        f"Ваша серия из {streak} дней под угрозой!\n"
                        f"Выполните задание «Слово дня», чтобы не прерывать серию."
                    )
                    try:
                        _send_telegram_message_sync(user.telegram_id, text)
                        nudged += 1
                    except Exception as e:
                        logger.error(f"Failed to nudge {user.id}: {e}")

        return {"nudged": nudged}

    return asyncio.run(_check())
