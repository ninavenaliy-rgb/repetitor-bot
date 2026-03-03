"""Celery tasks for lesson reminders."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger

from config.constants import POST_LESSON_FOLLOWUP_MINUTES, REMINDER_TIMINGS
from src.celery_app.celery_config import celery_app


def _send_telegram_message_sync(
    chat_id: int, text: str, reply_markup_data: dict | None = None
) -> None:
    """Send a Telegram message from a Celery task (sync context)."""

    async def _send():
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from config.settings import settings

        bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            markup = None
            if reply_markup_data:
                buttons = []
                for row in reply_markup_data.get("inline_keyboard", []):
                    btn_row = [
                        InlineKeyboardButton(
                            text=btn["text"], callback_data=btn["callback_data"]
                        )
                        for btn in row
                    ]
                    buttons.append(btn_row)
                markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        finally:
            await bot.session.close()

    asyncio.run(_send())


@celery_app.task(name="src.celery_app.tasks.reminder_tasks.scan_upcoming_bookings")
def scan_upcoming_bookings() -> dict:
    """Scan for upcoming bookings and schedule individual reminders."""

    async def _scan():
        from src.database.engine import get_session
        from src.database.repositories.booking_repo import BookingRepository

        now = datetime.now(timezone.utc)
        scheduled_count = 0

        async with get_session() as session:
            repo = BookingRepository(session)

            # Look 25 hours ahead to cover T-24h reminders
            window_end = now + timedelta(hours=25)
            bookings = await repo.get_needing_reminders(now, window_end)

            for booking in bookings:
                reminders_sent = booking.reminders_sent or {}

                for minutes_before in REMINDER_TIMINGS:
                    reminder_key = f"t_{minutes_before}"
                    if reminder_key in reminders_sent:
                        continue

                    reminder_time = booking.scheduled_at - timedelta(
                        minutes=minutes_before
                    )

                    if reminder_time <= now:
                        # Should have been sent already but wasn't — send now
                        send_lesson_reminder.delay(
                            str(booking.id), minutes_before
                        )
                        scheduled_count += 1
                    elif reminder_time <= window_end:
                        # Schedule for the future
                        send_lesson_reminder.apply_async(
                            args=[str(booking.id), minutes_before],
                            eta=reminder_time,
                        )
                        scheduled_count += 1

                # Schedule post-lesson follow-up
                followup_key = "post_lesson"
                if followup_key not in reminders_sent:
                    followup_time = booking.scheduled_at + timedelta(
                        minutes=booking.duration_min + POST_LESSON_FOLLOWUP_MINUTES
                    )
                    if now < followup_time <= window_end:
                        post_lesson_followup.apply_async(
                            args=[str(booking.id)],
                            eta=followup_time,
                        )
                        scheduled_count += 1

        return {"scanned": len(bookings) if bookings else 0, "scheduled": scheduled_count}

    return asyncio.run(_scan())


@celery_app.task(name="src.celery_app.tasks.reminder_tasks.send_lesson_reminder")
def send_lesson_reminder(booking_id: str, minutes_before: int) -> dict:
    """Send a reminder to the student about an upcoming lesson."""

    async def _send():
        import uuid

        from src.database.engine import get_session
        from src.database.repositories.booking_repo import BookingRepository

        # Load booking and student in a single session to avoid detached-object issues
        from src.database.repositories.user_repo import UserRepository
        from datetime import timedelta

        MOSCOW_OFFSET = timedelta(hours=3)

        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(uuid.UUID(booking_id))

            if not booking or booking.status != "planned":
                return {"status": "skipped", "reason": "not active"}

            # Mark this reminder as sent
            reminders_sent = booking.reminders_sent or {}
            reminder_key = f"t_{minutes_before}"
            if reminder_key in reminders_sent:
                return {"status": "skipped", "reason": "already sent"}

            reminders_sent[reminder_key] = datetime.now(timezone.utc).isoformat()
            await repo.update(booking, reminders_sent=reminders_sent)

            # Load student within same session
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(booking.user_id)
            if not user:
                return {"status": "error", "reason": "user not found"}

            # Snapshot values before session closes
            telegram_id = user.telegram_id
            user_id_str = str(user.id)
            lesson_time = (booking.scheduled_at + MOSCOW_OFFSET).strftime("%H:%M")

        time_map = {1440: "завтра", 120: "через 2 часа"}
        time_text = time_map.get(minutes_before, f"через {minutes_before} мин")

        text = (
            f"Напоминание: ваш урок <b>{time_text}</b> в {lesson_time} (МСК).\n\n"
            f"Подтвердите, пожалуйста, присутствие."
        )

        markup_data = {
            "inline_keyboard": [
                [
                    {"text": "Буду!", "callback_data": f"confirm_booking_{booking_id}"},
                    {"text": "Перенести", "callback_data": f"reschedule_{booking_id}"},
                ],
                [{"text": "Отменить урок", "callback_data": f"cancel_booking_{booking_id}"}],
            ]
        }

        _send_telegram_message_sync(telegram_id, text, markup_data)
        return {"status": "sent", "user_id": user_id_str, "minutes_before": minutes_before}

    return asyncio.run(_send())


@celery_app.task(name="src.celery_app.tasks.reminder_tasks.post_lesson_followup")
def post_lesson_followup(booking_id: str) -> dict:
    """Send post-lesson follow-up to tutor."""

    async def _send():
        import uuid

        from src.database.engine import get_session
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.tutor_repo import TutorRepository
        from src.database.repositories.user_repo import UserRepository

        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(uuid.UUID(booking_id))

            if not booking or booking.status != "planned":
                return {"status": "skipped"}

            reminders_sent = booking.reminders_sent or {}
            if "post_lesson" in reminders_sent:
                return {"status": "skipped", "reason": "already sent"}
            reminders_sent["post_lesson"] = datetime.now(timezone.utc).isoformat()
            await repo.update(booking, reminders_sent=reminders_sent)

        # Get tutor and student info
        async with get_session() as session:
            tutor_repo = TutorRepository(session)
            tutor = await tutor_repo.get_by_id(booking.tutor_id)
            user_repo = UserRepository(session)
            student = await user_repo.get_by_id(booking.user_id)

        if not tutor:
            return {"status": "error", "reason": "tutor not found"}

        student_name = student.name if student else "Ученик"
        text = (
            f"Урок с <b>{student_name}</b> — как прошёл?\n\n"
            f"Время: {booking.scheduled_at.strftime('%H:%M')}"
        )

        markup_data = {
            "inline_keyboard": [
                [
                    {"text": "Проведён", "callback_data": f"lesson_done_{booking_id}"},
                    {"text": "Неявка", "callback_data": f"lesson_noshow_{booking_id}"},
                ],
                [{"text": "Отменён", "callback_data": f"lesson_cancelled_{booking_id}"}],
            ]
        }

        _send_telegram_message_sync(tutor.telegram_id, text, markup_data)
        return {"status": "sent", "tutor_id": str(tutor.id)}

    return asyncio.run(_send())
