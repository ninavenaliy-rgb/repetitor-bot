"""Составление AI плана урока для репетитора."""

from __future__ import annotations

from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.keyboards.main_menu import tutor_reply_keyboard
from src.database.engine import get_session
from src.database.models import Tutor
from src.services.ai_service import AIService

router = Router(name="lesson_plan")
_ai_service = AIService()

GOAL_NAMES = {
    "general": "Разговорный английский",
    "business": "Бизнес-английский",
    "ielts": "IELTS / TOEFL",
    "oge_ege": "ОГЭ / ЕГЭ",
}


@router.message(F.text == "Составить план урока")
async def lesson_plan_start(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Запускаем генерацию плана урока — выбираем ученика."""
    if not db_tutor:
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        students = await repo.get_active_by_tutor(db_tutor.id)

    if not students:
        await message.answer(
            "Нет учеников. Добавьте ученика через «Добавить ученика».",
            reply_markup=tutor_reply_keyboard(),
        )
        return

    buttons = []
    for s in students[:10]:
        name = s.name or "Без имени"
        level = s.cefr_level or "?"
        buttons.append([
            InlineKeyboardButton(
                text=f"{name} ({level})",
                callback_data=f"lp_student_{s.id}",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "<b>Составить план урока</b>\n\nВыберите ученика:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("lp_student_"))
async def generate_plan_for_student(
    callback, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Генерируем план урока для выбранного ученика."""
    import uuid

    if not db_tutor:
        return

    user_id = uuid.UUID(callback.data.replace("lp_student_", ""))

    await callback.answer()
    thinking_msg = await callback.message.answer("Составляю план урока...")

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.booking_repo import BookingRepository

        u_repo = UserRepository(session)
        b_repo = BookingRepository(session)

        student = await u_repo.get_by_id(user_id)
        if not student:
            await thinking_msg.edit_text("Ученик не найден.")
            return

        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        recent_bookings = await b_repo.get_upcoming_by_tutor(
            db_tutor.id,
            from_dt=now - timedelta(days=60),
            to_dt=now,
        )

    student_bookings = [
        b for b in recent_bookings
        if b.user_id == user_id and b.status == "completed"
    ]

    recent_topics = ", ".join(
        b.topic for b in student_bookings[-5:] if b.topic
    ) or "не указаны"

    goal = GOAL_NAMES.get(student.goal or "", student.goal or "Общее развитие")
    cefr_level = student.cefr_level or "B1"
    duration = getattr(db_tutor, "default_duration_min", 60) or 60

    try:
        plan = await _ai_service.generate_lesson_plan(
            student_name=student.name or "Ученик",
            cefr_level=cefr_level,
            goal=goal,
            recent_topics=recent_topics,
            duration_min=duration,
            tutor_id=db_tutor.id,
        )
    except Exception as e:
        from loguru import logger
        logger.error(f"Lesson plan generation error: {e}")
        await thinking_msg.edit_text(
            "Не удалось сгенерировать план урока.\n"
            "Проверьте баланс OpenAI или попробуйте позже."
        )
        return

    # Сохраняем в следующий урок если есть
    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        b_repo = BookingRepository(session)
        upcoming = await b_repo.get_upcoming_by_tutor(
            db_tutor.id,
            from_dt=now,
            to_dt=now + timedelta(days=30),
        )
        next_booking = next(
            (b for b in upcoming if b.user_id == user_id and b.status == "planned"),
            None,
        )
        if next_booking:
            await b_repo.update(next_booking, ai_lesson_plan=plan)
            await session.commit()

    header = (
        f"<b>План урока: {student.name}</b>\n"
        f"Уровень: {cefr_level} | Цель: {goal} | {duration} мин\n"
        f"{'─' * 25}\n\n"
    )
    await thinking_msg.edit_text(header + plan[:3500])
