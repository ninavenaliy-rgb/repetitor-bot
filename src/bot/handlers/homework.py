"""Проверка домашнего задания через AI."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.bot.keyboards.main_menu import main_menu_keyboard
from src.bot.locales import t
from src.database.models import User
from src.services.ai_service import AIService
from src.utils.exceptions import RateLimitExceededError

router = Router(name="homework")
_ai_service = AIService()


class HomeworkStates(StatesGroup):
    """Состояния проверки домашки."""

    waiting_text = State()


@router.callback_query(F.data == "homework_start")
async def start_homework(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    """Начать проверку — попросить текст или фото."""
    lang = db_user.language if db_user else "ru"
    await state.set_state(HomeworkStates.waiting_text)
    await callback.answer()
    prompt_text = t(lang, "homework_prompt") + "\n\n📷 <i>Также можно отправить фотографию с текстом.</i>"
    await callback.message.edit_text(prompt_text)


MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB


@router.message(HomeworkStates.waiting_text, F.photo)
async def on_homework_photo(
    message: Message, state: FSMContext, db_user: User
) -> None:
    """Обработка фото домашки через GPT-4o Vision."""
    lang = db_user.language if db_user else "ru"

    photo = message.photo[-1]  # наибольшее разрешение
    if photo.file_size and photo.file_size > MAX_PHOTO_BYTES:
        await message.answer("Фото слишком большое (максимум 5 МБ). Попробуйте другой снимок.")
        return

    thinking_msg = await message.answer(t(lang, "homework_thinking"))

    try:
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        image_data = file_bytes.read()

        cefr_level = db_user.cefr_level or "B1"
        goal = db_user.goal or "general"
        feedback = await _ai_service.check_homework_from_image(
            image_bytes=image_data,
            cefr_level=cefr_level,
            user_id=db_user.id,
            goal=goal,
        )

        student_report = _ai_service.format_feedback_student(feedback, lang=lang)
        await thinking_msg.edit_text(student_report)

        await state.clear()
        await message.answer(
            t(lang, "what_next"),
            reply_markup=_after_homework_keyboard(lang, has_tutor=bool(db_user.tutor_id)),
        )

        if db_user.tutor_id:
            await _notify_tutor_homework(bot=message.bot, student=db_user, feedback=feedback)

        try:
            from src.services.score_service import update_student_score
            await update_student_score(db_user.id, "homework")
        except Exception:
            pass

    except RateLimitExceededError:
        await thinking_msg.edit_text(t(lang, "homework_limit"))
        await state.clear()
    except Exception as e:
        from loguru import logger
        logger.error(f"Photo homework check error: {e}")
        await thinking_msg.edit_text("Произошла ошибка. Попробуйте ещё раз позже.")
        await state.clear()


@router.message(HomeworkStates.waiting_text, F.text)
async def on_homework_text(
    message: Message, state: FSMContext, db_user: User
) -> None:
    """Обработка текста через AI."""
    text = message.text.strip()
    lang = db_user.language if db_user else "ru"

    if len(text) < 10:
        await message.answer(t(lang, "homework_too_short"))
        return

    if len(text) > 5000:
        await message.answer(t(lang, "homework_too_long"))
        return

    thinking_msg = await message.answer(t(lang, "homework_thinking"))

    try:
        cefr_level = db_user.cefr_level or "B1"
        goal = db_user.goal or "general"
        feedback = await _ai_service.check_homework(
            text=text,
            cefr_level=cefr_level,
            user_id=db_user.id,
            goal=goal,
        )

        # Отправляем ученику полный разбор
        student_report = _ai_service.format_feedback_student(feedback, lang=lang)
        await thinking_msg.edit_text(student_report)

        await state.clear()
        await message.answer(
            t(lang, "what_next"),
            reply_markup=main_menu_keyboard(lang),
        )

        # Отправляем репетитору отчёт (если есть)
        if db_user.tutor_id:
            await _notify_tutor_homework(
                bot=message.bot,
                student=db_user,
                feedback=feedback,
            )

        try:
            from src.services.score_service import update_student_score
            await update_student_score(db_user.id, "homework")
        except Exception:
            pass

    except RateLimitExceededError:
        await thinking_msg.edit_text(t(lang, "homework_limit"))
        await state.clear()

    except Exception as e:
        from loguru import logger
        logger.error(f"Homework check error: {e}")
        await thinking_msg.edit_text(
            "Произошла ошибка. Попробуйте ещё раз позже."
        )
        await state.clear()


def _after_homework_keyboard(lang: str, has_tutor: bool) -> InlineKeyboardMarkup:
    """Клавиатура после проверки домашки — предлагает записаться на урок."""
    buttons = []
    if has_tutor:
        buttons.append([
            InlineKeyboardButton(
                text="📅 Записаться на следующий урок",
                callback_data="booking_start",
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="✅ Проверить ещё одно задание",
            callback_data="homework_start",
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="🏠 Главное меню",
            callback_data="main_menu",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _notify_tutor_homework(bot, student: User, feedback) -> None:
    """Отправить репетитору краткий отчёт о домашней работе ученика."""
    from src.database.engine import get_session
    from src.database.repositories.tutor_repo import TutorRepository
    from loguru import logger

    try:
        async with get_session() as session:
            tutor_repo = TutorRepository(session)
            tutor = await tutor_repo.get_by_id(student.tutor_id)

        if not tutor or not tutor.telegram_id:
            return

        student_name = student.name or "Ученик"
        report = _ai_service.format_tutor_report(feedback, student_name=student_name)

        await bot.send_message(
            chat_id=tutor.telegram_id,
            text=report,
        )
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to notify tutor about homework: {e}")


# ─────────────────────────────────────────────────────────────────
# Голосовое домашнее задание — Whisper + AI-анализ
# ─────────────────────────────────────────────────────────────────

@router.message(F.voice)
async def on_voice_homework(message: Message, db_user: User, data: dict) -> None:
    """Принимаем голосовое, транскрибируем через Whisper и даём обратную связь."""
    # Репетиторам голосовой AI-разбор не нужен — только студентам
    if not db_user or data.get("db_tutor") is not None:
        return

    thinking_msg = await message.answer("Слушаю вашу запись...")

    try:
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        audio_data = file_bytes.read()

        await thinking_msg.edit_text("Расшифровываю речь...")
        transcript = await _ai_service.transcribe_voice(audio_data, filename="voice.ogg")

        if not transcript:
            await thinking_msg.edit_text(
                "Не удалось распознать речь. Попробуйте записать чище и тише."
            )
            return

        await thinking_msg.edit_text("Анализирую...")
        cefr_level = db_user.cefr_level or "B1"
        feedback = await _ai_service.check_pronunciation(
            transcript=transcript,
            cefr_level=cefr_level,
            user_id=db_user.id,
        )

        result = (
            f"<b>Голосовое задание</b>\n\n"
            f"<b>Ваш текст:</b>\n<i>{transcript[:500]}</i>\n\n"
            f"<b>Комментарий репетитора (AI):</b>\n{feedback}"
        )
        await thinking_msg.edit_text(result)

    except RateLimitExceededError:
        await thinking_msg.edit_text(
            "Вы исчерпали дневной лимит AI-проверок. Попробуйте завтра!"
        )
    except Exception as e:
        from loguru import logger
        logger.error(f"Voice homework error: {e}")
        await thinking_msg.edit_text(
            "Произошла ошибка при обработке голосового. Попробуйте ещё раз."
        )
