"""Тест уровня — адаптивное определение CEFR."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from src.bot.keyboards.placement_kb import answer_keyboard, result_keyboard
from src.bot.states.placement_states import PlacementStates
from src.database.engine import get_session
from src.database.models import User
from src.database.repositories.user_repo import UserRepository
from src.services.placement_service import PlacementService, PlacementSession

router = Router(name="placement")

_placement_service = PlacementService()

LEVEL_DESCRIPTIONS = {
    "A1": "Начинающий — базовые фразы",
    "A2": "Элементарный — простые темы",
    "B1": "Средний — повседневное общение",
    "B2": "Выше среднего — свободное общение",
    "C1": "Продвинутый — сложные тексты",
    "C2": "Профессиональный — свободное владение",
}

FREQUENCY_RU = {
    "A1": "2-3 урока в неделю",
    "A2": "2-3 урока в неделю",
    "B1": "2 урока в неделю",
    "B2": "1-2 урока в неделю",
    "C1": "1 урок в неделю",
    "C2": "1 урок в неделю (поддержка уровня)",
}


def _format_question(question: dict, number: int, total: int) -> str:
    """Формат вопроса для отображения."""
    return (
        f"<b>Вопрос {number} из {total}</b>\n\n"
        f"{question['question']}"
    )


def _format_result(result) -> str:
    """Формат результата теста."""
    desc = LEVEL_DESCRIPTIONS.get(result.cefr_level, "")
    freq = FREQUENCY_RU.get(result.cefr_level, result.suggested_frequency)
    return (
        f"<b>Тест завершён!</b>\n\n"
        f"Ваш уровень: <b>{result.cefr_level}</b>\n"
        f"{desc}\n\n"
        f"Правильных ответов: {result.total_correct} из {result.total_questions}\n"
        f"Уверенность: {result.confidence_pct}%\n\n"
        f"Рекомендация: <b>{freq}</b>\n\n"
        f"Хотите записаться на пробный урок?"
    )


@router.callback_query(F.data == "placement_start")
async def start_placement(callback: CallbackQuery, state: FSMContext) -> None:
    """Начать тест уровня."""
    session = PlacementSession()
    question = _placement_service.get_next_question(session)

    if not question:
        await callback.answer("Вопросы не загрузились. Попробуйте позже.")
        return

    await state.set_state(PlacementStates.answering)
    await state.update_data(
        placement_session={
            "answers": [],
            "current_level": session.current_level,
            "questions_asked": session.questions_asked,
        },
        current_question=question,
    )

    await callback.answer()
    await callback.message.edit_text(
        _format_question(question, 1, 12),
        reply_markup=answer_keyboard(question["options"]),
    )


@router.callback_query(PlacementStates.answering, F.data.startswith("placement_ans_"))
async def handle_answer(
    callback: CallbackQuery, state: FSMContext, db_user: User
) -> None:
    """Обработка ответа — следующий вопрос или результат."""
    selected_index = int(callback.data.split("_")[-1])
    data = await state.get_data()

    # Восстановление сессии
    session_data = data["placement_session"]
    session = PlacementSession(
        answers=[],
        current_level=session_data["current_level"],
        questions_asked=session_data["questions_asked"],
    )
    from src.services.placement_service import PlacementAnswer

    for a in session_data["answers"]:
        session.answers.append(
            PlacementAnswer(
                question_id=a["question_id"],
                cefr_level=a["cefr_level"],
                correct=a["correct"],
            )
        )

    question = data["current_question"]
    is_correct = _placement_service.submit_answer(session, question, selected_index)

    # Тест завершён?
    if session.is_complete:
        result = _placement_service.calculate_result(session)

        async with get_session() as db_session:
            repo = UserRepository(db_session)
            user = await repo.get_by_telegram_id(db_user.telegram_id)
            if user:
                await repo.update(user, cefr_level=result.cefr_level)

        await state.clear()
        await callback.answer()
        await callback.message.edit_text(
            _format_result(result),
            reply_markup=result_keyboard(),
        )
        return

    # Следующий вопрос
    next_question = _placement_service.get_next_question(session)
    if not next_question:
        result = _placement_service.calculate_result(session)
        async with get_session() as db_session:
            repo = UserRepository(db_session)
            user = await repo.get_by_telegram_id(db_user.telegram_id)
            if user:
                await repo.update(user, cefr_level=result.cefr_level)

        await state.clear()
        await callback.answer()
        await callback.message.edit_text(
            _format_result(result),
            reply_markup=result_keyboard(),
        )
        return

    # Сохранение состояния
    serialized_answers = [
        {
            "question_id": a.question_id,
            "cefr_level": a.cefr_level,
            "correct": a.correct,
        }
        for a in session.answers
    ]

    await state.update_data(
        placement_session={
            "answers": serialized_answers,
            "current_level": session.current_level,
            "questions_asked": session.questions_asked,
        },
        current_question=next_question,
    )

    feedback = "Верно!" if is_correct else "Неверно"
    await callback.answer(feedback)
    await callback.message.edit_text(
        _format_question(next_question, session.question_number, 12),
        reply_markup=answer_keyboard(next_question["options"]),
    )
