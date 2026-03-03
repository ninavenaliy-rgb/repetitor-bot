"""Обработчик отзывов и предложений от студентов и репетиторов."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from config.settings import settings
from src.bot.keyboards.main_menu import main_menu_reply_keyboard, tutor_reply_keyboard
from src.database.models import Tutor, User

router = Router(name="feedback")


class FeedbackStates(StatesGroup):
    waiting_message = State()


@router.message(F.text.in_({"💬 Отзывы и предложения", "💬 Отзывы"}))
async def feedback_start(
    message: Message, state: FSMContext, db_user: User,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """Предложить написать отзыв."""
    await state.set_state(FeedbackStates.waiting_message)
    await message.answer(
        "✍️ <b>Отзывы и предложения</b>\n\n"
        "Напишите ваш отзыв, пожелание или предложение — "
        "я передам его разработчику.\n\n"
        "Можно написать что угодно: что нравится, что хотелось бы улучшить, "
        "или идеи для новых функций.\n\n"
        "Для отмены напишите /start."
    )


@router.message(FeedbackStates.waiting_message)
async def feedback_receive(
    message: Message, state: FSMContext, db_user: User,
    db_tutor: Optional[Tutor] = None,
) -> None:
    """Принимаем отзыв и пересылаем в feedback-чат."""
    await state.clear()
    lang = db_user.language if db_user else "ru"
    is_tutor = db_tutor is not None

    text = message.text or message.caption or ""
    if not text.strip():
        kb = tutor_reply_keyboard() if is_tutor else main_menu_reply_keyboard(lang)
        await message.answer("Отзыв не может быть пустым. Попробуйте ещё раз.", reply_markup=kb)
        return

    # Подтверждение пользователю
    kb = tutor_reply_keyboard() if is_tutor else main_menu_reply_keyboard(lang)
    await message.answer("✅ Спасибо за ваш отзыв! Мы обязательно его рассмотрим.", reply_markup=kb)

    # Пересылка в feedback-чат
    if not settings.feedback_chat_id:
        return

    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    role_label = "👨‍🏫 Репетитор" if is_tutor else "👤 Студент"
    extra = f"📊 Уровень: {db_user.cefr_level or '—'}\n" if not is_tutor else ""

    user_info = (
        f"{role_label}: <b>{db_user.name or 'Без имени'}</b>\n"
        f"🆔 TG: <code>{db_user.telegram_id}</code>\n"
        f"{extra}"
        f"🕐 {now}\n\n"
        f"💬 <b>Отзыв:</b>\n{text}"
    )

    try:
        await message.bot.send_message(chat_id=settings.feedback_chat_id, text=user_info)
    except Exception:
        pass
