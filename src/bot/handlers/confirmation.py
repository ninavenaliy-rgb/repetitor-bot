"""Подтверждение/отмена уроков из напоминаний."""

from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from loguru import logger

from src.bot.keyboards.main_menu import main_menu_keyboard
from src.services.booking_service import BookingService

router = Router(name="confirmation")
_booking_service = BookingService()

DEMO_CALENDAR_ID = "primary"


@router.callback_query(F.data.startswith("confirm_booking_"))
async def on_confirm_booking(callback: CallbackQuery) -> None:
    """Ученик подтверждает присутствие."""
    booking_id = callback.data.replace("confirm_booking_", "")

    try:
        await _booking_service.confirm_booking(uuid.UUID(booking_id))
        await callback.answer("Подтверждено!")
        await callback.message.edit_text(
            "Отлично! Вы подтвердили присутствие. До встречи на уроке!"
        )
    except Exception as e:
        logger.error(f"confirm_booking {booking_id}: {e}")
        await callback.answer("Ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("cancel_booking_"))
async def on_cancel_booking(callback: CallbackQuery) -> None:
    """Ученик отменяет урок."""
    booking_id = callback.data.replace("cancel_booking_", "")

    try:
        await _booking_service.cancel_booking(
            uuid.UUID(booking_id), DEMO_CALENDAR_ID
        )
        await callback.answer("Отменено")
        await callback.message.edit_text(
            "Урок отменён.\n"
            "Хотите записаться на другое время?",
            reply_markup=main_menu_keyboard(),
        )
    except Exception as e:
        logger.error(f"cancel_booking {booking_id}: {e}")
        await callback.answer("Ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("lesson_done_"))
async def on_lesson_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Репетитор отмечает урок как проведённый."""
    booking_id = callback.data.replace("lesson_done_", "")

    try:
        booking = await _booking_service.complete_booking(uuid.UUID(booking_id))
        await callback.answer("Урок завершён!")
        await callback.message.edit_text(
            "Урок отмечен как проведённый!\n\n"
            "Напишите тему урока текстом или нажмите кнопку ниже.",
            reply_markup=main_menu_keyboard(),
        )
        # Update student Academic Score after lesson completion
        if booking and hasattr(booking, "user_id"):
            try:
                from src.services.score_service import update_student_score
                await update_student_score(booking.user_id, "lesson")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"lesson_done {booking_id}: {e}")
        await callback.answer("Ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("lesson_noshow_"))
async def on_lesson_noshow(callback: CallbackQuery) -> None:
    """Репетитор отмечает неявку."""
    booking_id = callback.data.replace("lesson_noshow_", "")

    from src.database.engine import get_session
    from src.database.repositories.booking_repo import BookingRepository

    try:
        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(uuid.UUID(booking_id))
            if booking:
                await repo.update(booking, status="no_show")

        await callback.answer("Отмечено")
        await callback.message.edit_text("Урок отмечен как неявка.")
    except Exception as e:
        logger.error(f"lesson_noshow {booking_id}: {e}")
        await callback.answer("Ошибка. Попробуйте ещё раз.")


@router.callback_query(F.data.startswith("lesson_cancelled_"))
async def on_lesson_cancelled(callback: CallbackQuery) -> None:
    """Репетитор отменяет урок."""
    booking_id = callback.data.replace("lesson_cancelled_", "")

    try:
        await _booking_service.cancel_booking(
            uuid.UUID(booking_id), DEMO_CALENDAR_ID
        )
        await callback.answer("Отменено")
        await callback.message.edit_text("Урок отменён.")
    except Exception as e:
        logger.error(f"lesson_cancelled {booking_id}: {e}")
        await callback.answer("Ошибка. Попробуйте ещё раз.")
