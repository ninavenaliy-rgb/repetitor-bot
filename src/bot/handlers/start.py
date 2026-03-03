"""Обработчик /start и выбор цели обучения."""

from __future__ import annotations

from typing import Optional

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.main_menu import (
    after_goal_keyboard,
    goal_keyboard,
    main_menu_keyboard,
    main_menu_reply_keyboard,
    tutor_reply_keyboard,
)
from src.bot.locales import (
    ALL_BTN_BOOK,
    ALL_BTN_HOMEWORK,
    ALL_BTN_MY_LESSONS,
    ALL_BTN_PROFILE,
    t,
)
from src.bot.states.registration import RegistrationStates
from src.database.engine import get_session
from src.database.models import Tutor, User
from src.database.repositories.user_repo import UserRepository

router = Router(name="start")

TUTOR_WELCOME = (
    "Привет, {name}!\n\n"
    "Вы вошли как <b>репетитор</b>.\n"
    "Учеников: <b>{students}</b>\n"
    "Тариф: <b>{plan}</b>\n\n"
    "Используйте меню ниже для управления."
)

TUTOR_WELCOME_NEW = (
    "Привет, {name}! 👋\n\n"
    "Вы вошли как <b>репетитор</b>.\n"
    "Тариф: <b>{plan}</b>\n\n"
    "Похоже, учеников пока нет — давайте это исправим!\n\n"
    "<b>Быстрый старт:</b>\n"
    "1️⃣ Нажмите <b>«Добавить ученика»</b>\n"
    "2️⃣ Отправьте ученику личную ссылку на бота\n"
    "3️⃣ Запишите первый урок\n\n"
    "Остальное бот сделает сам — напомнит ученику, проверит домашку, посчитает доходы."
)

GOAL_NAMES = {
    "general": "goal_general",
    "business": "goal_business",
    "ielts": "goal_ielts",
    "toefl": "goal_ielts",
    "oge_ege": "goal_oge_ege",
}


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("inv_")))
async def cmd_start_invite(
    message: Message, state: FSMContext, db_user: User, command: CommandStart = None
) -> None:
    """Handle /start inv_TOKEN — bind student to tutor via invite link."""
    args = message.text.split(maxsplit=1)
    token = args[1].replace("inv_", "") if len(args) > 1 else ""
    lang = db_user.language if db_user else "ru"

    if not token:
        await message.answer(t(lang, "invite_invalid"))
        return

    from src.database.repositories.tutor_repo import TutorRepository

    async with get_session() as session:
        tutor_repo = TutorRepository(session)
        tutor = await tutor_repo.get_by_invite_token(token)
        if not tutor:
            await message.answer(t(lang, "invite_invalid"))
            return
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        if user and user.tutor_id != tutor.id:
            await user_repo.update(user, tutor_id=tutor.id)
        await session.commit()

    await state.clear()
    await message.answer(
        t(lang, "invite_success", name=tutor.name or "репетитор"),
        reply_markup=main_menu_reply_keyboard(lang),
    )


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("sref_")))
async def cmd_start_student_ref(
    message: Message, state: FSMContext, db_user: User
) -> None:
    """Handle /start sref_CODE — bind student referral."""
    args = message.text.split(maxsplit=1)
    code = args[1].replace("sref_", "") if len(args) > 1 else ""
    lang = db_user.language if db_user else "ru"

    if not code or not db_user:
        await cmd_start(message, state, db_user)
        return

    async with get_session() as session:
        repo = UserRepository(session)
        referrer = await repo.get_by_student_referral_code(code)

        if not referrer or referrer.id == db_user.id:
            # Invalid code or self-referral — just show normal start
            await cmd_start(message, state, db_user)
            return

        student = await repo.get_by_id(db_user.id)
        if student and not student.referred_by_user_id:
            await repo.update(student, referred_by_user_id=referrer.id)
        await session.commit()

    # Notify referrer's tutor if any
    if referrer.tutor_id:
        try:
            from src.database.repositories.tutor_repo import TutorRepository
            async with get_session() as session2:
                tutor = await TutorRepository(session2).get_by_id(referrer.tutor_id)
            if tutor and tutor.telegram_id:
                await message.bot.send_message(
                    chat_id=tutor.telegram_id,
                    text=(
                        f"🎁 <b>{db_user.name or 'Новый ученик'}</b> зарегистрировался "
                        f"по реферальной ссылке <b>{referrer.name or 'ученика'}</b>!"
                    ),
                )
        except Exception:
            pass

    await cmd_start(message, state, db_user)


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, db_user: User, db_tutor: Optional[Tutor] = None
) -> None:
    """Обработка /start — панель для репетитора, меню для ученика."""
    await state.clear()

    if db_tutor:
        async with get_session() as session:
            from src.database.repositories.user_repo import UserRepository

            repo = UserRepository(session)
            count = await repo.count_by_tutor(db_tutor.id)

        plan = getattr(db_tutor, "subscription_plan", "BASIC") or "BASIC"

        if count == 0:
            text = TUTOR_WELCOME_NEW.format(
                name=db_tutor.name or "репетитор",
                plan=plan,
            )
        else:
            text = TUTOR_WELCOME.format(
                name=db_tutor.name or "репетитор",
                students=count,
                plan=plan,
            )
        await message.answer(text, reply_markup=tutor_reply_keyboard())
        return

    lang = db_user.language if db_user else "ru"

    if db_user.goal and db_user.cefr_level:
        goal_key = GOAL_NAMES.get(db_user.goal, "goal_not_set")
        text = t(lang, "welcome_back",
                 name=db_user.name or "друг",
                 level=db_user.cefr_level or t(lang, "level_not_set"),
                 goal=t(lang, goal_key))
        await message.answer(text, reply_markup=main_menu_reply_keyboard(lang))
    elif db_user.goal:
        # Has goal but no level — show language picker to let them continue
        from src.bot.handlers.language import language_keyboard
        await message.answer(t(lang, "choose_language"), reply_markup=language_keyboard())
        await state.set_state(RegistrationStates.waiting_language)
    else:
        # Brand new user — pick language first
        from src.bot.handlers.language import language_keyboard
        await message.answer(t("ru", "choose_language"), reply_markup=language_keyboard())
        await state.set_state(RegistrationStates.waiting_language)


@router.callback_query(F.data.startswith("goal_"))
async def on_goal_selected(
    callback: CallbackQuery, state: FSMContext, db_user: User
) -> None:
    """Обработка выбора цели."""
    goal = callback.data.replace("goal_", "")
    lang = db_user.language if db_user else "ru"
    goal_key = GOAL_NAMES.get(goal, "goal_not_set")
    goal_name = t(lang, goal_key)

    async with get_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(db_user.telegram_id)
        if user:
            await repo.update(user, goal=goal)

    await callback.answer()
    await callback.message.edit_text(
        t(lang, "goal_chosen", goal=goal_name),
        reply_markup=after_goal_keyboard(lang),
    )
    await state.clear()


@router.callback_query(F.data == "skip_placement")
async def on_skip_placement(callback: CallbackQuery, db_user: User) -> None:
    """Пропуск теста — показать главное меню."""
    lang = db_user.language if db_user else "ru"
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        t(lang, "skip_placement"),
        reply_markup=main_menu_reply_keyboard(lang),
    )


# --- Обработка нажатий reply-клавиатуры (постоянное меню ученика) ---


@router.message(F.text.in_(ALL_BTN_BOOK))
async def reply_booking(message: Message, state: FSMContext, db_user: User) -> None:
    """Переход к записи на урок из reply-меню."""
    await state.clear()
    from src.bot.handlers.booking import start_booking_from_message

    await start_booking_from_message(message, state)


@router.message(F.text.in_(ALL_BTN_MY_LESSONS))
async def reply_my_lessons(message: Message, db_user: User) -> None:
    """Показать ближайшие уроки."""
    from datetime import datetime, timedelta, timezone

    from src.database.repositories.booking_repo import BookingRepository

    lang = db_user.language if db_user else "ru"
    tutor_id = db_user.tutor_id
    if not tutor_id:
        await message.answer(t(lang, "no_tutor"))
        return

    async with get_session() as session:
        repo = BookingRepository(session)
        now = datetime.now(timezone.utc)
        bookings = await repo.get_upcoming_by_tutor(
            tutor_id=tutor_id,
            from_dt=now,
            to_dt=now + timedelta(days=30),
        )

    my_bookings = [b for b in bookings if b.user_id == db_user.id]

    if not my_bookings:
        await message.answer(t(lang, "no_lessons", btn=t(lang, "btn_book")))
        return

    lines = [t(lang, "upcoming_lessons")]
    for b in my_bookings[:5]:
        dt = b.scheduled_at
        lines.append(f"  {dt.strftime('%d.%m %H:%M')} — {b.duration_min} мин")

    await message.answer("\n".join(lines))


@router.message(F.text.in_(ALL_BTN_HOMEWORK))
async def reply_homework(message: Message, state: FSMContext, db_user: User) -> None:
    """Переход к проверке домашки из reply-меню."""
    from src.bot.handlers.homework import HomeworkStates

    lang = db_user.language if db_user else "ru"
    await state.clear()
    await state.set_state(HomeworkStates.waiting_text)
    await message.answer(t(lang, "homework_prompt"))


@router.message(F.text.in_(ALL_BTN_PROFILE))
async def reply_profile(message: Message, db_user: User) -> None:
    """Показать профиль ученика с Academic Score."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.database.repositories.metrics_repo import MetricsRepository
    from src.services.score_service import score_percentile

    lang = db_user.language if db_user else "ru"
    goal_key = GOAL_NAMES.get(db_user.goal or "", "goal_not_set")
    goal_name = t(lang, goal_key)
    level = db_user.cefr_level or t(lang, "level_not_set")
    name = db_user.name or "—"

    text = t(lang, "profile_body", name=name, level=level, goal=goal_name)

    # Academic Score block
    async with get_session() as session:
        metrics = await MetricsRepository(session).get_by_user(db_user.id)

    if metrics and metrics.academic_score > 0:
        score = metrics.academic_score
        pct = score_percentile(score)
        streak = metrics.streak
        streak_line = f"🔥 Серия: <b>{streak} дней</b>\n" if streak >= 3 else ""
        text += (
            f"\n\n🎓 <b>Academic Score: {score}</b>\n"
            f"{streak_line}"
            f"👥 Выше <b>{pct}%</b> учеников вашего уровня"
        )
    else:
        pct_progress = getattr(db_user, "progress_level", 0) or 0
        if pct_progress > 0:
            from src.services.analytics_service import _progress_bar
            text += f"\n📈 Прогресс: <b>{_progress_bar(pct_progress)}</b>"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_retake_test"), callback_data="placement_start"
                )
            ],
        ]
    )
    await message.answer(text, reply_markup=kb)



@router.callback_query(F.data == "main_menu")
async def on_main_menu(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    """Возврат в главное меню."""
    lang = db_user.language if db_user else "ru"
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        t(lang, "skip_placement"), reply_markup=main_menu_reply_keyboard(lang)
    )
