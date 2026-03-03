"""Async reminder service — runs inside the bot process, no Celery/Redis needed."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from config.constants import POST_LESSON_FOLLOWUP_MINUTES, REMINDER_TIMINGS

MOSCOW_OFFSET = timedelta(hours=3)
SCAN_INTERVAL_SEC = 300  # every 5 minutes


async def _send(bot: Bot, chat_id: int, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    except Exception as e:
        logger.warning(f"reminder_service: failed to send to {chat_id}: {e}")


def _student_markup(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Буду!", callback_data=f"confirm_booking_{booking_id}"),
            InlineKeyboardButton(text="Перенести", callback_data=f"reschedule_{booking_id}"),
        ],
        [InlineKeyboardButton(text="Отменить урок", callback_data=f"cancel_booking_{booking_id}")],
    ])


def _tutor_markup(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить урок", callback_data=f"lesson_cancelled_{booking_id}")],
    ])


async def _scan_and_send(bot: Bot) -> None:
    from src.database.engine import get_session
    from src.database.repositories.booking_repo import BookingRepository
    from src.database.repositories.tutor_repo import TutorRepository
    from src.database.repositories.user_repo import UserRepository

    now = datetime.now(timezone.utc)
    # Look ahead far enough to cover T-24h reminder
    window_end = now + timedelta(hours=25)

    try:
        async with get_session() as session:
            repo = BookingRepository(session)
            bookings = await repo.get_needing_reminders(now, window_end)

            for booking in bookings:
                booking_id = str(booking.id)
                reminders_sent = booking.reminders_sent or {}
                updated = False

                for minutes_before in REMINDER_TIMINGS:
                    reminder_key = f"t_{minutes_before}"
                    if reminder_key in reminders_sent:
                        continue

                    reminder_time = booking.scheduled_at - timedelta(minutes=minutes_before)

                    # Send if it's time (reminder_time <= now) or overdue
                    if reminder_time > now:
                        continue

                    # Load student and tutor within the same session
                    user_repo = UserRepository(session)
                    tutor_repo = TutorRepository(session)

                    student = await user_repo.get_by_id(booking.user_id)
                    tutor = await tutor_repo.get_by_id(booking.tutor_id)

                    if not student or not tutor:
                        logger.warning(f"reminder_service: missing student/tutor for booking {booking_id}")
                        continue

                    lesson_time = (booking.scheduled_at + MOSCOW_OFFSET).strftime("%H:%M")
                    lesson_date = (booking.scheduled_at + MOSCOW_OFFSET).strftime("%d.%m")
                    student_name = student.name or "Ученик"

                    time_map = {1440: "завтра", 120: "через 2 часа"}
                    time_text = time_map.get(minutes_before, f"через {minutes_before} мин")

                    # --- Student message ---
                    student_text = (
                        f"Напоминание: ваш урок <b>{time_text}</b> — {lesson_date} в {lesson_time} (МСК).\n\n"
                        f"Подтвердите, пожалуйста, присутствие."
                    )
                    await _send(bot, student.telegram_id, student_text, _student_markup(booking_id))

                    # --- Tutor message ---
                    tutor_text = (
                        f"Напоминание: урок с <b>{student_name}</b> — <b>{time_text}</b>, "
                        f"{lesson_date} в {lesson_time} (МСК)."
                    )
                    await _send(bot, tutor.telegram_id, tutor_text, _tutor_markup(booking_id))

                    logger.info(
                        f"Reminder T-{minutes_before}m sent: booking={booking_id}, "
                        f"student={student.telegram_id}, tutor={tutor.telegram_id}"
                    )

                    reminders_sent[reminder_key] = now.isoformat()
                    updated = True

                # Post-lesson follow-up for tutor
                followup_key = "post_lesson"
                if followup_key not in reminders_sent:
                    followup_time = booking.scheduled_at + timedelta(
                        minutes=booking.duration_min + POST_LESSON_FOLLOWUP_MINUTES
                    )
                    if followup_time <= now:
                        tutor_repo = TutorRepository(session)
                        user_repo = UserRepository(session)
                        tutor = await tutor_repo.get_by_id(booking.tutor_id)
                        student = await user_repo.get_by_id(booking.user_id)

                        if tutor:
                            student_name = student.name if student else "Ученик"
                            text = (
                                f"Урок с <b>{student_name}</b> завершён?\n\n"
                                f"Отметьте результат:"
                            )
                            markup = InlineKeyboardMarkup(inline_keyboard=[
                                [
                                    InlineKeyboardButton(text="Проведён ✅", callback_data=f"lesson_done_{booking_id}"),
                                    InlineKeyboardButton(text="Неявка ❌", callback_data=f"lesson_noshow_{booking_id}"),
                                ],
                                [InlineKeyboardButton(text="Отменён", callback_data=f"lesson_cancelled_{booking_id}")],
                            ])
                            await _send(bot, tutor.telegram_id, text, markup)

                        reminders_sent[followup_key] = now.isoformat()
                        updated = True

                if updated:
                    await repo.update(booking, reminders_sent=reminders_sent)

    except Exception as e:
        logger.error(f"reminder_service scan error: {e}")


async def start_reminder_loop(bot: Bot) -> None:
    """Background loop — scan for reminders every 5 minutes."""
    logger.info("Reminder service started (interval=5min)")
    while True:
        await _scan_and_send(bot)
        await asyncio.sleep(SCAN_INTERVAL_SEC)


# --- Daily Word of the Day broadcast ---

_daily_word_sent_date: Optional[str] = None  # "YYYY-MM-DD" in MSK


async def _broadcast_daily_word(bot: Bot) -> None:
    from sqlalchemy import and_, select

    from src.database.engine import get_session
    from src.database.models import User
    from src.services.engagement_service import EngagementService
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    service = EngagementService()
    sent_count = 0

    try:
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

                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✍️ Составить предложение",
                        callback_data="engagement_use_word",
                    )],
                ])
                await _send(bot, user.telegram_id, text, markup)
                sent_count += 1
            except Exception as e:
                logger.error(f"daily_word: failed for user {user.id}: {e}")

        logger.info(f"Daily word sent to {sent_count}/{len(users)} users")
    except Exception as e:
        logger.error(f"daily_word broadcast error: {e}")


async def start_daily_word_loop(bot: Bot) -> None:
    """Send Word of the Day at 09:00 MSK every day."""
    global _daily_word_sent_date
    logger.info("Daily word loop started (fires at 09:00 MSK)")

    while True:
        now_msk = datetime.now(timezone.utc) + MOSCOW_OFFSET
        today_str = now_msk.strftime("%Y-%m-%d")

        if now_msk.hour == 9 and _daily_word_sent_date != today_str:
            _daily_word_sent_date = today_str
            await _broadcast_daily_word(bot)

        await asyncio.sleep(60)  # check every minute


# --- Daily Churn Risk scan ---

_churn_checked_date: Optional[str] = None  # "YYYY-MM-DD" in MSK

_REENGAGEMENT_MESSAGES = [
    (
        "Привет! 👋 Давно не заходил на практику.\n\n"
        "Всего 5 минут с «Словом дня» — и серия продолжается. "
        "Ты уже вложил время в учёбу, не дай прогрессу остановиться!"
    ),
    (
        "Эй! Твой репетитор верит в тебя 💪\n\n"
        "Загляни сегодня — выполни одно задание и поддержи свой прогресс. "
        "Маленький шаг сегодня = большой результат через месяц."
    ),
    (
        "Пропуски бывают у всех, но лучшие ученики возвращаются! 🎯\n\n"
        "Открой бота и сделай хотя бы одно упражнение — это занимает меньше минуты."
    ),
]


async def _run_churn_scan(bot: Bot) -> None:
    from sqlalchemy import select

    from src.database.engine import get_session
    from src.database.models import Tutor, User
    from src.services.churn_service import (
        assess_churn_risk,
        format_churn_for_tutor,
        get_at_risk_students,
    )

    import random

    try:
        async with get_session() as session:
            result = await session.execute(
                select(Tutor).where(Tutor.is_active == True)
            )
            tutors = list(result.scalars().all())

        logger.info(f"churn_scan: checking {len(tutors)} tutors")

        for tutor in tutors:
            if not tutor.telegram_id:
                continue
            try:
                at_risk = await get_at_risk_students(tutor.id)
                high_risk = [s for s in at_risk if s["risk_level"] == "HIGH"]

                if not high_risk:
                    continue

                # Notify tutor
                lines = [f"⚠️ <b>Ученики в зоне риска ({len(high_risk)} чел.)</b>\n"]
                for student_info in high_risk[:5]:
                    from src.services.churn_service import ChurnResult
                    churn = await assess_churn_risk(student_info["user_id"])
                    lines.append(format_churn_for_tutor(student_info["name"], churn))
                    lines.append("")

                await _send(bot, tutor.telegram_id, "\n".join(lines))
                logger.info(
                    f"churn_scan: notified tutor {tutor.telegram_id} about {len(high_risk)} HIGH-risk students"
                )

            except Exception as e:
                logger.error(f"churn_scan: tutor {tutor.id} error: {e}")

        # Re-engagement: send motivating message to HIGH-risk students
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.is_active == True)
            )
            all_users = list(result.scalars().all())

        for user in all_users:
            try:
                churn = await assess_churn_risk(user.id)
                if churn.risk_level == "HIGH":
                    msg = random.choice(_REENGAGEMENT_MESSAGES)
                    await _send(bot, user.telegram_id, msg)
            except Exception:
                pass

        logger.info("churn_scan: re-engagement messages sent")

    except Exception as e:
        logger.error(f"churn_scan error: {e}")


async def start_churn_check_loop(bot: Bot) -> None:
    """Run churn risk scan daily at 10:00 MSK."""
    global _churn_checked_date
    logger.info("Churn check loop started (fires at 10:00 MSK)")

    while True:
        now_msk = datetime.now(timezone.utc) + MOSCOW_OFFSET
        today_str = now_msk.strftime("%Y-%m-%d")

        if now_msk.hour == 10 and _churn_checked_date != today_str:
            _churn_checked_date = today_str
            await _run_churn_scan(bot)

        await asyncio.sleep(60)


# --- Trial expiry notifications ---

_trial_notified_date: Optional[str] = None  # "YYYY-MM-DD" in MSK


async def _run_trial_expiry_check(bot: Bot) -> None:
    """Notify tutors when trial ends in 1 day or has just expired."""
    from sqlalchemy import select

    from src.database.engine import get_session
    from src.database.models_subscription import Subscription, SubscriptionStatus

    now = datetime.now(timezone.utc)

    try:
        async with get_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.status == SubscriptionStatus.TRIAL.value
                )
            )
            trial_subs = list(result.scalars().all())

        for sub in trial_subs:
            if not sub.trial_end:
                continue

            days_left = (sub.trial_end - now).days

            if days_left == 1:
                # 1 day left — urgent nudge
                from src.database.engine import get_session as gs
                from src.database.repositories.tutor_repo import TutorRepository
                async with gs() as s2:
                    tutor = await TutorRepository(s2).get_by_id(sub.tutor_id)
                if tutor and tutor.telegram_id:
                    text = (
                        "⏰ <b>Пробный период заканчивается завтра!</b>\n\n"
                        "Чтобы не потерять доступ к боту, оформите подписку:\n"
                        "📦 СТАРТ — 990₽/мес\n"
                        "💎 ПРО — 1990₽/мес\n\n"
                        "Нажмите <b>«💎 Моя подписка»</b> в меню."
                    )
                    await _send(bot, tutor.telegram_id, text)
                    logger.info(f"Trial expiry notice (1d) sent to tutor {tutor.telegram_id}")

            elif days_left <= 0:
                # Expired — expire the subscription
                from src.database.engine import get_session as gs
                from src.database.repositories.tutor_repo import TutorRepository
                from src.database.repositories.subscription_repo import SubscriptionRepository
                async with gs() as s2:
                    tutor = await TutorRepository(s2).get_by_id(sub.tutor_id)
                    sub_repo = SubscriptionRepository(s2)
                    live_sub = await sub_repo.get_by_id(sub.id)
                    if live_sub and live_sub.status == SubscriptionStatus.TRIAL.value:
                        await sub_repo.update(live_sub, status=SubscriptionStatus.EXPIRED.value)
                        await s2.commit()
                if tutor and tutor.telegram_id:
                    text = (
                        "❌ <b>Пробный период завершён</b>\n\n"
                        "Ваш 7-дневный бесплатный доступ закончился.\n\n"
                        "Оформите подписку, чтобы продолжить работу с учениками:\n"
                        "📦 СТАРТ — 990₽/мес\n"
                        "💎 ПРО — 1990₽/мес\n\n"
                        "Нажмите <b>«💎 Моя подписка»</b> в меню."
                    )
                    await _send(bot, tutor.telegram_id, text)
                    logger.info(f"Trial expired notice sent to tutor {tutor.telegram_id}")

    except Exception as e:
        logger.error(f"trial_expiry_check error: {e}")


async def start_trial_expiry_loop(bot: Bot) -> None:
    """Check trial expiry daily at 11:00 MSK."""
    global _trial_notified_date
    logger.info("Trial expiry loop started (fires at 11:00 MSK)")

    while True:
        now_msk = datetime.now(timezone.utc) + MOSCOW_OFFSET
        today_str = now_msk.strftime("%Y-%m-%d")

        if now_msk.hour == 11 and _trial_notified_date != today_str:
            _trial_notified_date = today_str
            await _run_trial_expiry_check(bot)

        await asyncio.sleep(60)
