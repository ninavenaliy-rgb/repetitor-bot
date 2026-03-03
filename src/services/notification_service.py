"""Notification service — parent reports and student reminders."""

from __future__ import annotations

import datetime
from typing import Optional

from aiogram import Bot
from loguru import logger

from src.database.models import Booking, User, Tutor


async def send_parent_report(
    bot: Bot,
    booking: Booking,
    student: User,
    tutor: Tutor,
    next_lesson_dt: Optional[datetime.datetime] = None,
) -> bool:
    """Send lesson summary to parent after lesson is marked done.

    Returns True if message was sent successfully.
    """
    if not student.parent_telegram_id or not student.notify_parent:
        return False

    topic = booking.topic or "не указана"
    homework = booking.homework or "не задано"
    summary = booking.lesson_summary or ""
    date_str = booking.scheduled_at.strftime("%d.%m.%Y %H:%M")

    next_str = ""
    if next_lesson_dt:
        next_str = f"\n📅 Следующее занятие: {next_lesson_dt.strftime('%d.%m.%Y %H:%M')}"

    text = (
        f"📚 <b>Отчёт о занятии</b>\n"
        f"Ученик: <b>{student.name}</b>\n"
        f"Репетитор: <b>{tutor.name}</b>\n"
        f"Дата: {date_str}\n\n"
        f"📖 Тема: {topic}\n"
        f"📝 Домашнее задание: {homework}"
    )
    if summary:
        text += f"\n\n💬 Комментарий репетитора:\n{summary}"
    text += next_str

    try:
        await bot.send_message(
            chat_id=student.parent_telegram_id,
            text=text,
            parse_mode="HTML",
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to send parent report to {student.parent_telegram_id}: {e}")
        return False


async def send_low_package_warning(bot: Bot, student: User, lessons_remaining: int) -> None:
    """Notify student when package is almost exhausted."""
    if not student.telegram_id:
        return
    try:
        await bot.send_message(
            chat_id=student.telegram_id,
            text=(
                f"⚠️ В вашем пакете уроков осталось <b>{lessons_remaining}</b> "
                f"{'урок' if lessons_remaining == 1 else 'урока'}.\n"
                "Свяжитесь с репетитором для продления."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Failed to send low-package warning to {student.telegram_id}: {e}")
