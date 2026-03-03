"""Tutor self-registration via /start tutor or /start ref_CODE deep link."""

from __future__ import annotations

import html
import secrets
import string

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config.settings import settings
from src.bot.states.tutor_states import TutorRegistrationStates
from src.database.engine import get_session
from src.database.repositories.tutor_repo import TutorRepository
from src.database.repositories.referral_repo import ReferralRepository

router = Router(name="tutor_registration")


def _cancel_registration_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with cancel button for registration flow."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить регистрацию", callback_data="tutor_reg_cancel")]
        ]
    )


def _generate_referral_code() -> str:
    """Generate a short 6-char uppercase referral code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


@router.message(CommandStart(deep_link=True, magic=F.args == "tutor"))
async def cmd_start_tutor(message: Message, state: FSMContext) -> None:
    """Entry point: /start tutor — begin tutor registration."""
    await state.clear()
    await state.update_data(referrer_code=None)
    await state.set_state(TutorRegistrationStates.entering_name)
    await message.answer(
        "Добро пожаловать в регистрацию репетитора!\n\n"
        "Введите ваше имя (или имя и фамилию):",
        reply_markup=_cancel_registration_keyboard()
    )


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("ref_")))
async def cmd_start_ref(message: Message, state: FSMContext) -> None:
    """Entry point: /start ref_CODE — register as tutor with referrer."""
    args: str = message.text.split(maxsplit=1)[1] if " " in message.text else ""
    ref_code = args.replace("ref_", "").strip().upper()

    await state.clear()
    await state.update_data(referrer_code=ref_code)
    await state.set_state(TutorRegistrationStates.entering_name)
    await message.answer(
        "Добро пожаловать! Вас пригласил коллега-репетитор.\n\n"
        "Введите ваше имя (или имя и фамилию):",
        reply_markup=_cancel_registration_keyboard()
    )


@router.message(TutorRegistrationStates.entering_name)
async def reg_name(message: Message, state: FSMContext) -> None:
    """Save name, ask for subjects."""
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 200:
        await message.answer("Пожалуйста, введите корректное имя (до 200 символов):")
        return
    await state.update_data(name=name)
    await state.set_state(TutorRegistrationStates.entering_subjects)
    await message.answer(
        f"Отлично, {name}!\n\n"
        "Какие предметы вы преподаёте?\n"
        "Введите через запятую, например: <i>Английский, Немецкий</i>",
        reply_markup=_cancel_registration_keyboard()
    )


@router.message(TutorRegistrationStates.entering_subjects)
async def reg_subjects(message: Message, state: FSMContext) -> None:
    """Save subjects, ask for default lesson price."""
    subjects = message.text.strip() if message.text else ""
    if not subjects:
        await message.answer("Введите хотя бы один предмет:")
        return
    await state.update_data(subjects=subjects[:500])
    await state.set_state(TutorRegistrationStates.entering_price)
    await message.answer(
        "Укажите стоимость одного урока в рублях (например: <b>1500</b>).\n"
        "Это значение будет использоваться по умолчанию:",
        reply_markup=_cancel_registration_keyboard()
    )


@router.message(TutorRegistrationStates.entering_price)
async def reg_price(message: Message, state: FSMContext) -> None:
    """Save price, create Tutor, send invite + referral links."""
    text = message.text.strip() if message.text else ""

    # Проверка на пустую строку
    if not text:
        await message.answer(
            "❌ Пожалуйста, введите цену урока.\n\n"
            "Например: <b>1500</b> или <b>2000</b>"
        )
        return

    # Проверка на нечисловое значение
    try:
        from decimal import Decimal, InvalidOperation
        # Удаляем все кроме цифр, точки, запятой и минуса
        cleaned_text = text.replace(" ", "").replace(",", ".")
        price = Decimal(cleaned_text)

        if price <= 0:
            await message.answer(
                "❌ Цена должна быть положительным числом.\n\n"
                "Введите сумму больше 0, например: <b>1500</b>"
            )
            return

        if price > Decimal("100000"):
            await message.answer(
                "❌ Слишком большая сумма (максимум 100,000₽).\n\n"
                "Введите реальную цену урока, например: <b>1500</b>"
            )
            return

    except (InvalidOperation, ValueError):
        await message.answer(
            "❌ Неверный формат цены.\n\n"
            "Введите числом (только цифры), например:\n"
            "• <b>1500</b>\n"
            "• <b>2000</b>\n"
            "• <b>2500</b>"
        )
        return

    data = await state.get_data()
    name: str = data.get("name", "Репетитор")
    subjects: str = data.get("subjects", "English")
    referrer_code: str | None = data.get("referrer_code")

    invite_token = secrets.token_urlsafe(32)
    referral_code = _generate_referral_code()

    try:
        async with get_session() as session:
            tutor_repo = TutorRepository(session)

            # Проверяем, не зарегистрирован ли уже
            existing = await tutor_repo.get_by_telegram_id(message.from_user.id)
            if existing:
                await state.clear()
                await message.answer(
                    "Вы уже зарегистрированы как репетитор!\n"
                    "Отправьте /start чтобы открыть панель управления."
                )
                return

            # Находим реферера
            referred_by_id = None
            if referrer_code:
                ref_repo = ReferralRepository(session)
                referrer = await ref_repo.get_by_referral_code(referrer_code)
                if referrer:
                    referred_by_id = referrer.id

            # Гарантируем уникальность referral_code
            ref_check_repo = ReferralRepository(session)
            for _ in range(10):  # max 10 attempts to avoid infinite loop
                check = await ref_check_repo.get_by_referral_code(referral_code)
                if check is None:
                    break
                referral_code = _generate_referral_code()

            new_tutor = await tutor_repo.create(
                telegram_id=message.from_user.id,
                name=name,
                subjects=subjects,
                default_lesson_price=price,
                invite_token=invite_token,
                referral_code=referral_code,
                referred_by_id=referred_by_id,
                registration_state="active",
            )
            tutor_id = new_tutor.id  # UUID set in Python, safe to read before commit
    except Exception as e:
        from loguru import logger
        logger.error(f"Tutor creation failed for telegram_id={message.from_user.id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании аккаунта.\n\n"
            "Попробуйте ввести цену ещё раз или напишите /start."
        )
        return  # Keep FSM state so user can retry

    # Activate 7-day trial subscription
    try:
        from src.services.subscription_service import SubscriptionService
        await SubscriptionService().create_trial_subscription(tutor_id, plan_code="START")
    except Exception as e:
        from loguru import logger
        logger.warning(f"Trial creation failed for tutor {tutor_id}: {e}")

    await state.clear()

    bot_username = settings.bot_username
    if bot_username:
        invite_link = f"https://t.me/{bot_username}?start=inv_{invite_token}"
        ref_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
    else:
        invite_link = None
        ref_link = None

    ref_note = (
        "\n\n<i>Вы зарегистрированы по реферальной ссылке — ваш пригласитель получит бонус.</i>"
        if referred_by_id else ""
    )

    safe_name = html.escape(name)

    # Онбординг: 3 шага + информация о триале
    onboarding = (
        f"🎉 <b>{safe_name}, добро пожаловать в Repetitor Bot!</b>\n\n"
        f"<b>У вас 7 дней бесплатного доступа</b> — попробуйте все функции без оплаты.\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Как начать работу — 3 шага:</b>\n\n"
        f"<b>1. Добавьте первого ученика</b>\n"
        f"   Нажмите кнопку <b>«Добавить ученика»</b> в меню ниже\n\n"
        f"<b>2. Отправьте ученику ссылку</b>\n"
    )

    if invite_link:
        onboarding += (
            f"   Ученик переходит по ней и сразу видит расписание:\n"
            f"   <code>{invite_link}</code>\n\n"
        )
    else:
        onboarding += "   Ученик открывает бота и вводит ваш код\n\n"

    onboarding += (
        f"<b>3. Запишите первый урок</b>\n"
        f"   Зайдите в карточку ученика → «Записать на урок»\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"<b>Что умеет бот:</b>\n"
        f"✅ Автозапись и напоминания ученикам\n"
        f"✅ Проверка домашних заданий через ИИ\n"
        f"✅ Учёт оплат и пакетов уроков\n"
        f"✅ Составление планов уроков через ИИ\n"
        f"✅ Аналитика доходов\n"
    )

    if ref_link:
        onboarding += (
            f"\n👥 <b>Пригласите коллегу-репетитора</b> и получите бонус:\n"
            f"<code>{ref_link}</code>"
        )

    onboarding += ref_note

    # Клавиатура быстрых действий для старта
    quick_start_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить первого ученика",
                    callback_data="tp_add_student",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 Тарифы и подписка",
                    callback_data="subscription_menu",
                )
            ],
        ]
    )

    from src.bot.keyboards.main_menu import tutor_reply_keyboard
    await message.answer(onboarding, reply_markup=tutor_reply_keyboard())
    await message.answer(
        "👆 Используйте меню выше или нажмите кнопку:",
        reply_markup=quick_start_kb,
    )


@router.callback_query(F.data == "tutor_reg_cancel")
async def cancel_tutor_registration(callback, state: FSMContext) -> None:
    """Cancel tutor registration and return to start."""
    await state.clear()
    await callback.answer("Регистрация отменена")
    await callback.message.edit_text(
        "Регистрация репетитора отменена.\n\n"
        "Отправьте /start чтобы вернуться в главное меню."
    )
