"""Взаимодействие с ежедневным контентом (Слово дня)."""

from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from urllib.parse import quote

from config.constants import EngagementEventType
from src.bot.locales import ALL_BTN_WORD
from src.database.models import User
from src.services.engagement_service import EngagementService
from src.services.score_service import (
    STREAK_MILESTONES as _MILESTONES,
    build_share_card,
    compute_score,
    milestone_congrats,
    update_student_score,
)

router = Router(name="engagement")
_engagement_service = EngagementService()


@router.message(F.text.in_(ALL_BTN_WORD))
async def on_word_of_day_button(message: Message, state: FSMContext, db_user: User) -> None:
    """Ученик нажал кнопку «Слово дня» — показываем слово и ждём предложение."""
    await state.clear()
    thinking = await message.answer("Подбираю слово дня...")

    word = await _engagement_service.get_word_of_day_ai(db_user.cefr_level or "B2")
    streak = await _engagement_service.get_streak(db_user.id)
    text = _engagement_service.format_word_of_day(word, streak)

    # Сохраняем слово в FSM чтобы потом проверить предложение
    await state.update_data(word_of_day=word.get("word", ""))
    await state.set_state("waiting_sentence")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Составить предложение", callback_data="engagement_use_word")],
    ])

    await thinking.delete()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "engagement_use_word")
async def on_use_word(callback: CallbackQuery, state: FSMContext) -> None:
    """Напоминание написать предложение (из рассылки или после показа слова)."""
    await callback.answer()
    await callback.message.answer(
        "Напишите предложение с этим словом.\n"
        "Я проверю, всё ли правильно!"
    )
    await state.set_state("waiting_sentence")


@router.message(StateFilter("waiting_sentence"), F.text)
async def on_sentence_submitted(
    message: Message, state: FSMContext, db_user: User
) -> None:
    """Обработка предложения для Слова дня — AI проверяет правильность."""
    sentence = message.text.strip()

    data = await state.get_data()
    word_of_day = data.get("word_of_day", "")

    thinking = await message.answer("Проверяю ваше предложение...")

    ai_feedback = await _check_sentence_with_ai(sentence, word_of_day, db_user)

    streak = await _engagement_service.record_interaction(
        user_id=db_user.id,
        event_type=EngagementEventType.WORD_OF_DAY.value,
        completed=ai_feedback["is_correct"],
    )

    await state.clear()
    await thinking.delete()

    streak_text = f"\nСерия: <b>{streak} дней</b> подряд!" if streak > 1 else ""

    if ai_feedback["is_correct"]:
        await message.answer(
            f"Отлично! {ai_feedback['comment']}{streak_text}\n\n"
            "Практикуйтесь каждый день, чтобы не прерывать серию!"
        )
    else:
        corrected = ai_feedback.get("corrected", "")
        corrected_text = f"\n\nПравильный вариант:\n<i>{corrected}</i>" if corrected else ""
        await message.answer(
            f"Почти! {ai_feedback['comment']}{corrected_text}\n\n"
            "Попробуйте завтра с новым словом!"
        )

    # Update Academic Score in background (fire-and-forget, non-blocking)
    if ai_feedback["is_correct"]:
        try:
            await update_student_score(db_user.id, "engagement")
        except Exception:
            pass

    # Milestone check — send share card on 7/14/30/60/100 days
    if ai_feedback["is_correct"] and streak in _MILESTONES:
        await _send_milestone_share_card(message, db_user, streak)


async def _send_milestone_share_card(message: Message, db_user: User, streak: int) -> None:
    """Отправить поздравление + share карточку при достижении milestone стрика."""
    from config.settings import settings
    from src.database.engine import get_session
    from src.database.repositories.user_repo import UserRepository
    import secrets
    import string

    score = compute_score(db_user.cefr_level, streak)
    congrats = milestone_congrats(streak, score)

    # Получаем или генерируем реферальный код
    async with get_session() as session:
        repo = UserRepository(session)
        student = await repo.get_by_id(db_user.id)
        if not student.student_referral_code:
            alphabet = string.ascii_uppercase + string.digits
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            while await repo.get_by_student_referral_code(code):
                code = "".join(secrets.choice(alphabet) for _ in range(6))
            await repo.update(student, student_referral_code=code)
            await session.commit()
            ref_code = code
        else:
            ref_code = student.student_referral_code

    name = db_user.name or "Ученик"
    bot_username = settings.bot_username
    ref_link = f"https://t.me/{bot_username}?start=sref_{ref_code}"

    card_text = build_share_card(name, db_user.cefr_level, streak, ref_link)

    # Telegram share URL — открывает диалог пересылки
    share_text = quote(
        f"Мой Academic Score — {score}. Учу английский с AI-репетитором!"
    )
    share_url = f"https://t.me/share/url?url={quote(ref_link)}&text={share_text}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться достижением", url=share_url)],
    ])

    await message.answer(
        f"🏆 <b>{congrats}</b>\n\n{card_text}",
        reply_markup=markup,
    )


async def _check_sentence_with_ai(sentence: str, word: str, db_user: User) -> dict:
    """AI проверяет грамматику и использование слова."""
    try:
        from src.services.ai_service import AIService
        ai = AIService()
        level = getattr(db_user, "cefr_level", None) or "B1"

        word_context = f'The student was asked to use the word "{word}" in a sentence. ' if word else ""
        system_prompt = (
            f"{word_context}"
            f"Student CEFR level: {level}. "
            "Check if this English sentence is grammatically correct and natural. "
            "Return ONLY valid JSON: "
            '{"is_correct": true, "comment": "1-2 sentences in Russian praising the student", '
            '"corrected": ""} '
            "OR "
            '{"is_correct": false, "comment": "1-2 sentences in Russian explaining the error", '
            '"corrected": "corrected version of the sentence"}'
        )

        response = await ai._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": sentence},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.2,
        )
        data = json.loads(response.choices[0].message.content or "{}")
        return {
            "is_correct": bool(data.get("is_correct", False)),
            "comment": data.get("comment", ""),
            "corrected": data.get("corrected", ""),
        }
    except Exception:
        return {
            "is_correct": True,
            "comment": "Предложение принято!",
            "corrected": "",
        }
