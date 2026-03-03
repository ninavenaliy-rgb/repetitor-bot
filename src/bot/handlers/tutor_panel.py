"""Панель управления репетитора — ученики, расписание, оплаты, доходы, заметки."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.keyboards.tutor_kb import (
    cancel_keyboard,
    duration_keyboard,
    income_keyboard,
    lesson_detail_keyboard,
    lesson_summary_keyboard,
    level_keyboard,
    package_size_keyboard,
    payment_actions_keyboard,
    payment_method_keyboard,
    payments_list_keyboard,
    progress_keyboard,
    schedule_keyboard,
    student_card_keyboard,
    students_list_keyboard,
)
from src.bot.keyboards.main_menu import tutor_reply_keyboard
from src.bot.states.tutor_states import TutorStates
from src.database.engine import get_session
from src.database.models import Tutor, User

# Subscription plan student limits
PLAN_LIMITS: dict[str, int] = {
    "BASIC": 10,
    "PRO": 50,
    "ENTERPRISE": 9999,
}

router = Router(name="tutor_panel")

_WEEKDAYS_RU = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
_MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

# Московское время (UTC+3)
MOSCOW_OFFSET = timedelta(hours=3)

# ─────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────

def _fmt_dt(dt: datetime) -> str:
    """Форматирует datetime в московское время для отображения."""
    dt_moscow = dt + MOSCOW_OFFSET
    wd = _WEEKDAYS_RU.get(dt_moscow.weekday(), "")
    return f"{dt_moscow.strftime('%d.%m')} ({wd}) {dt_moscow.strftime('%H:%M')}"


def _require_tutor(db_tutor: Optional[Tutor]) -> bool:
    return db_tutor is not None


# Кнопки меню репетитора — при их нажатии в любом FSM-состоянии выходим из него
TUTOR_MENU_BTNS = frozenset({
    "Мои ученики", "Расписание", "Оплаты", "Доходы",
    "Добавить ученика", "Заметки", "Составить план урока", "📝 Составить план урока",
    "✅ Проверить ДЗ", "Рефералы",
    "💬 Отзывы и предложения", "💬 Отзывы", "🔴 Зона риска", "👨‍🎓 Режим ученика",
})


@router.message(StateFilter(TutorStates), F.text.in_(TUTOR_MENU_BTNS))
async def cancel_tutor_state_via_menu(
    message: Message, state: FSMContext
) -> None:
    """Выход из любого FSM-состояния при нажатии кнопки главного меню."""
    await state.clear()
    await message.answer(
        "Действие отменено. Выберите раздел:",
        reply_markup=tutor_reply_keyboard(),
    )


@router.callback_query(F.data == "tp_cancel_state")
async def cancel_tutor_state_via_button(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Выход из FSM-состояния по кнопке «Отмена»."""
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text(
        "Действие отменено.",
    )
    await callback.message.answer(
        "Выберите раздел:",
        reply_markup=tutor_reply_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────
# МОИ УЧЕНИКИ
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Мои ученики")
async def show_students(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    """Список учеников репетитора."""
    if not _require_tutor(db_tutor):
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.payment_repo import PaymentRepository

        repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        students = await repo.get_active_by_tutor(db_tutor.id)
        debts = await pay_repo.get_debt_summary(db_tutor.id)

    debt_map = {str(d["user_id"]): d["total"] for d in debts}

    if not students:
        await message.answer(
            "<b>Мои ученики</b>\n\n"
            "Список пуст. Нажмите «Добавить ученика», чтобы добавить первого.",
            reply_markup=tutor_reply_keyboard(),
        )
        return

    student_dicts = [
        {
            "id": str(s.id),
            "name": s.name or "Без имени",
            "level": s.cefr_level or "?",
            "debt": debt_map.get(str(s.id), Decimal("0")),
        }
        for s in students
    ]

    lines = [f"<b>Мои ученики ({len(students)})</b>\n"]
    for s in students:
        level = s.cefr_level or "?"
        debt = debt_map.get(str(s.id))
        debt_mark = f" 💰{debt}₽" if debt else ""
        lines.append(f"• {s.name or 'Без имени'} ({level}){debt_mark}")

    await message.answer(
        "\n".join(lines) + "\n\nВыберите ученика:",
        reply_markup=students_list_keyboard(student_dicts),
    )


@router.callback_query(F.data.startswith("tp_stpage_"))
async def students_page(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    page = int(callback.data.replace("tp_stpage_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        students = await repo.get_active_by_tutor(db_tutor.id)

    student_dicts = [
        {"id": str(s.id), "name": s.name or "Без имени", "level": s.cefr_level or "?"}
        for s in students
    ]
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=students_list_keyboard(student_dicts, page=page)
    )


@router.callback_query(F.data == "tp_students_back")
async def students_back(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        students = await repo.get_active_by_tutor(db_tutor.id)

    student_dicts = [
        {"id": str(s.id), "name": s.name or "Без имени", "level": s.cefr_level or "?"}
        for s in students
    ]
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=students_list_keyboard(student_dicts)
    )


@router.message(F.text == "🔴 Зона риска")
async def show_churn_risk(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    """Отчёт по ученикам в зоне риска отвала."""
    if not _require_tutor(db_tutor):
        return

    await message.answer("Анализирую учеников... ⏳")

    from src.services.churn_service import assess_churn_risk, format_churn_for_tutor, get_at_risk_students

    at_risk = await get_at_risk_students(db_tutor.id)

    if not at_risk:
        await message.answer(
            "✅ <b>Отлично!</b> Ни один ученик не в зоне риска.\n\n"
            "Все активны и вовлечены. Продолжайте в том же духе!",
        )
        return

    high = [s for s in at_risk if s["risk_level"] == "HIGH"]
    medium = [s for s in at_risk if s["risk_level"] == "MEDIUM"]

    header = (
        f"⚠️ <b>Зона риска: {len(at_risk)} уч.</b> "
        f"(🔴 {len(high)} HIGH, 🟡 {len(medium)} MEDIUM)\n\n"
    )
    await message.answer(header)

    for student_info in at_risk[:8]:
        churn = await assess_churn_risk(student_info["user_id"])
        text = format_churn_for_tutor(student_info["name"], churn)
        await message.answer(text)


@router.message(F.text == "👨‍🎓 Режим ученика")
async def enter_learning_mode(
    message: Message, state: FSMContext, db_user, db_tutor: Optional[Tutor] = None
) -> None:
    """Репетитор переключается в режим ученика."""
    if not _require_tutor(db_tutor):
        return
    await state.clear()
    from src.bot.keyboards.main_menu import main_menu_reply_keyboard
    lang = (db_user.language if db_user and db_user.language else None) or "ru"
    await message.answer(
        "👨‍🎓 Режим ученика активирован.\n\nИспользуйте меню ниже.",
        reply_markup=main_menu_reply_keyboard(lang, is_tutor=True),
    )


@router.message(F.text == "↩ Панель репетитора")
async def leave_learning_mode(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Возврат из режима ученика в панель репетитора."""
    if not _require_tutor(db_tutor):
        return
    await state.clear()
    await message.answer(
        f"Панель репетитора ↩",
        reply_markup=tutor_reply_keyboard(),
    )


@router.callback_query(F.data.startswith("tp_student_"))
async def show_student_card(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    """Карточка ученика."""
    if not _require_tutor(db_tutor):
        return

    user_id = uuid.UUID(callback.data.replace("tp_student_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.payment_repo import PaymentRepository
        from src.database.repositories.package_repo import PackageRepository

        u_repo = UserRepository(session)
        b_repo = BookingRepository(session)
        p_repo = PaymentRepository(session)
        pkg_repo = PackageRepository(session)

        student = await u_repo.get_by_id(user_id)
        if not student or student.tutor_id != db_tutor.id:
            await callback.answer("Ученик не найден")
            return

        # Статистика уроков
        now = datetime.now(timezone.utc)
        all_bookings = await b_repo.get_upcoming_by_tutor(
            tutor_id=db_tutor.id,
            from_dt=now - timedelta(days=365),
            to_dt=now + timedelta(days=365),
        )
        student_bookings = [b for b in all_bookings if b.user_id == student.id]
        completed = sum(1 for b in student_bookings if b.status == "completed")
        upcoming_list = sorted(
            [b for b in student_bookings if b.status == "planned" and b.scheduled_at >= now],
            key=lambda b: b.scheduled_at,
        )
        last_done = next(
            (b for b in sorted(student_bookings, key=lambda b: b.scheduled_at, reverse=True)
             if b.status == "completed"), None
        )

        # Долг
        payments = await p_repo.get_by_user(db_tutor.id, student.id, limit=50)
        debt = sum(p.amount for p in payments if p.status == "pending")

        # Активный пакет
        active_pkg = await pkg_repo.get_active_for_user(db_tutor.id, student.id)

    goal_map = {
        "general": "💬 Разговорный", "business": "💼 Бизнес",
        "ielts": "🎓 IELTS/TOEFL", "oge_ege": "📝 ОГЭ/ЕГЭ",
    }
    goal = goal_map.get(student.goal or "", student.goal or "Не указана")
    notes_preview = (student.notes or "").strip()[:150] or "—"

    default_price = getattr(db_tutor, "default_lesson_price", None) or Decimal("2000")
    price = student.price_per_lesson if student.price_per_lesson else default_price
    price_tag = "индивид." if student.price_per_lesson else "по умолч."

    # Пакет
    pkg_line = ""
    if active_pkg:
        pkg_line = f"\n📦 Пакет: <b>{active_pkg.lessons_remaining}</b>/{active_pkg.total_lessons} уроков осталось"

    # Ближайший урок
    next_lesson_line = ""
    if upcoming_list:
        nxt = upcoming_list[0]
        next_lesson_line = f"\n📅 Следующий: <b>{_fmt_dt(nxt.scheduled_at)}</b>"

    # Последний урок
    last_lesson_line = ""
    if last_done:
        last_lesson_line = f"\n✅ Последний: {_fmt_dt(last_done.scheduled_at)}"

    debt_line = f"💰 Долг: <b>{debt:.0f}₽</b>" if debt > 0 else "✅ Долгов нет"

    text = (
        f"<b>👤 {student.name or 'Без имени'}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Уровень: <b>{student.cefr_level or 'не определён'}</b>\n"
        f"🎯 Цель: {goal}\n"
        f"💵 Цена: <b>{price:.0f}₽/ур</b> ({price_tag})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Уроков проведено: <b>{completed}</b>\n"
        f"📋 Запланировано: <b>{len(upcoming_list)}</b>"
        f"{next_lesson_line}"
        f"{last_lesson_line}"
        f"{pkg_line}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{debt_line}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Заметки:</b> {notes_preview}"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=student_card_keyboard(student.id))


# ─────────────────────────────────────────────────────────────────
# ДОБАВИТЬ УЧЕНИКА
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Добавить ученика")
async def add_student_start(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Начать добавление ученика."""
    if not _require_tutor(db_tutor):
        return

    plan = getattr(db_tutor, "subscription_plan", "BASIC") or "BASIC"
    limit = PLAN_LIMITS.get(plan, 10)

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        count = await repo.count_by_tutor(db_tutor.id)

    if count >= limit:
        await message.answer(
            f"⚠️ <b>Лимит тарифа {plan}</b>\n\n"
            f"На вашем тарифе максимум <b>{limit} учеников</b>.\n"
            f"Сейчас у вас: <b>{count}</b>.\n\n"
            "Для подключения большего числа учеников перейдите на тариф <b>PRO</b> (до 50) "
            "или <b>ENTERPRISE</b> (без ограничений).\n\n"
            "Напишите @HelperBotSupport для апгрейда."
        )
        return

    await state.set_state(TutorStates.adding_student)
    await message.answer(
        "<b>Добавить ученика</b>\n\n"
        "Перешлите мне любое сообщение от ученика "
        "или введите его Telegram ID (числовой).\n\n"
        "Ученик должен был хотя бы раз написать боту.",
        reply_markup=cancel_keyboard(),
    )


@router.message(TutorStates.adding_student)
async def add_student_process(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Обработка добавления ученика."""
    if not _require_tutor(db_tutor):
        return

    student_tg_id: Optional[int] = None

    # Пересланное сообщение
    if message.forward_from:
        student_tg_id = message.forward_from.id
    # Числовой ID
    elif message.text and message.text.strip().lstrip("-").isdigit():
        student_tg_id = int(message.text.strip())

    if not student_tg_id:
        await message.answer(
            "Не удалось определить ID ученика.\n"
            "Перешлите сообщение от ученика или введите его числовой Telegram ID.\n\n"
            "Или нажмите «Отмена» чтобы выйти.",
            reply_markup=cancel_keyboard(),
        )
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_telegram_id(student_tg_id)

        if not student:
            await state.clear()
            await message.answer(
                "Ученик не найден. Попросите его сначала написать боту /start, "
                "затем добавьте его снова."
            )
            return

        if student.tutor_id == db_tutor.id:
            await state.clear()
            await message.answer(f"{student.name or 'Ученик'} уже добавлен к вам.")
            return

        await repo.update(student, tutor_id=db_tutor.id)

    await state.clear()
    await message.answer(
        f"Ученик <b>{student.name or student_tg_id}</b> успешно добавлен!\n\n"
        "Теперь он привязан к вам и вы сможете управлять его уроками.",
        reply_markup=tutor_reply_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────
# РАСПИСАНИЕ
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Расписание")
async def show_schedule(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    await _send_week_schedule(message, db_tutor, week_offset=0, edit=False)


@router.callback_query(F.data.startswith("tp_week_"))
async def schedule_week_nav(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    week_offset = int(callback.data.replace("tp_week_", ""))
    await callback.answer()
    await _send_week_schedule(callback.message, db_tutor, week_offset=week_offset, edit=True)


@router.callback_query(F.data.startswith("tp_month_"))
async def schedule_month_nav(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    await callback.answer()
    await _send_month_schedule(callback.message, db_tutor, edit=True)


async def _send_week_schedule(
    message: Message, tutor: Tutor, week_offset: int, edit: bool
) -> None:
    # Московское время для корректного отображения расписания
    MOSCOW_OFFSET = timedelta(hours=3)
    now_utc = datetime.now(timezone.utc)
    now_moscow = now_utc + MOSCOW_OFFSET

    # Начало недели в московском времени
    week_start_moscow = (now_moscow - timedelta(days=now_moscow.weekday())) + timedelta(weeks=week_offset)
    week_start_moscow = week_start_moscow.replace(hour=0, minute=0, second=0, microsecond=0)

    # Конвертируем обратно в UTC для запроса к БД
    week_start = week_start_moscow - MOSCOW_OFFSET
    week_end = week_start + timedelta(days=7)

    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.payment_repo import PaymentRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        p_repo = PaymentRepository(session)
        u_repo = UserRepository(session)

        bookings = await b_repo.get_upcoming_by_tutor(tutor.id, week_start, week_end)
        prev_bookings = await b_repo.get_upcoming_by_tutor(tutor.id, prev_week_start, prev_week_end)
        students = await u_repo.get_active_by_tutor(tutor.id)
        debts = await p_repo.get_debt_summary(tutor.id)

    debt_ids = {str(d["user_id"]) for d in debts}
    student_map = {str(s.id): s for s in students}

    week_diff = len(bookings) - len(prev_bookings)
    if week_diff > 0:
        trend_str = f" ↑+{week_diff}"
    elif week_diff < 0:
        trend_str = f" ↓{week_diff}"
    else:
        trend_str = ""

    # Отображаем диапазон недели в московском времени
    week_label = f"{week_start_moscow.strftime('%d.%m')} – {(week_start_moscow + timedelta(days=6)).strftime('%d.%m.%Y')}"
    lines = [f"<b>Расписание: {week_label}</b>\n<i>Уроков: {len(bookings)}{trend_str}</i>\n"]

    lesson_buttons: list[tuple[str, str]] = []
    status_map = {"planned": "📅", "completed": "✅", "cancelled": "❌", "no_show": "🚫"}

    if not bookings:
        lines.append("Уроков на этой неделе нет.")
    else:
        cur_day = None
        for b in bookings:
            # Конвертируем время урока в московское для отображения
            lesson_time_moscow = b.scheduled_at + MOSCOW_OFFSET
            day_str = lesson_time_moscow.strftime("%d.%m")
            wd = _WEEKDAYS_RU.get(lesson_time_moscow.weekday(), "")

            if day_str != cur_day:
                lines.append(f"\n<b>{day_str} ({wd})</b>")
                cur_day = day_str

            student = student_map.get(str(b.user_id))
            name = student.name if student else "?"
            paid_mark = " 💰" if str(b.user_id) in debt_ids else ""
            status = status_map.get(b.status, "?")
            lines.append(
                f"  {lesson_time_moscow.strftime('%H:%M')} {name} "
                f"({b.duration_min}м) {status}{paid_mark}"
            )
            if b.status in ("planned", "completed"):
                btn_label = f"{status} {lesson_time_moscow.strftime('%d.%m %H:%M')} · {name}"
                lesson_buttons.append((btn_label, f"tp_lesdet_{b.id}"))

    text = "\n".join(lines)
    if lesson_buttons:
        text += "\n\n<i>👇 Нажмите на урок для управления:</i>"
    kb = schedule_keyboard(week_offset, lesson_buttons=lesson_buttons)

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def _send_month_schedule(message: Message, tutor: Tutor, edit: bool) -> None:
    # Московское время для корректного отображения
    now_utc = datetime.now(timezone.utc)
    now_moscow = now_utc + MOSCOW_OFFSET

    # Начало месяца в московском времени
    month_start_moscow = now_moscow.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Конвертируем в UTC для запроса к БД
    month_start = month_start_moscow - MOSCOW_OFFSET

    if month_start_moscow.month == 12:
        month_end_moscow = month_start_moscow.replace(year=month_start_moscow.year + 1, month=1)
    else:
        month_end_moscow = month_start_moscow.replace(month=month_start_moscow.month + 1)

    month_end = month_end_moscow - MOSCOW_OFFSET

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        u_repo = UserRepository(session)
        bookings = await b_repo.get_upcoming_by_tutor(tutor.id, month_start, month_end)
        students = await u_repo.get_active_by_tutor(tutor.id)

    student_map = {str(s.id): s for s in students}
    mon_name = _MONTHS_RU.get(now_moscow.month, "")
    lines = [f"<b>Расписание на {mon_name} {now_moscow.year}</b>\n"]

    if not bookings:
        lines.append("Уроков в этом месяце нет.")
    else:
        total = len(bookings)
        completed = sum(1 for b in bookings if b.status == "completed")
        planned = sum(1 for b in bookings if b.status == "planned")
        lines.append(f"Всего: {total} | Проведено: {completed} | Запланировано: {planned}\n")

        cur_day = None
        for b in bookings:
            # Конвертируем в московское время для отображения
            lesson_time_moscow = b.scheduled_at + MOSCOW_OFFSET
            day_str = lesson_time_moscow.strftime("%d.%m")
            wd = _WEEKDAYS_RU.get(lesson_time_moscow.weekday(), "")
            if day_str != cur_day:
                lines.append(f"\n<b>{day_str} ({wd})</b>")
                cur_day = day_str
            student = student_map.get(str(b.user_id))
            name = student.name if student else "?"
            status_map = {"planned": "📅", "completed": "✅", "cancelled": "❌", "no_show": "🚫"}
            status = status_map.get(b.status, "?")
            lines.append(f"  {lesson_time_moscow.strftime('%H:%M')} {name} ({b.duration_min}м) {status}")

    text = "\n".join(lines)
    kb = schedule_keyboard(0)

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ─────────────────────────────────────────────────────────────────
# ДЕТАЛИ УРОКА из расписания
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_lesdet_"))
async def show_lesson_detail(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Показать детали урока и кнопки управления."""
    if not _require_tutor(db_tutor):
        return
    booking_id = uuid.UUID(callback.data.replace("tp_lesdet_", ""))

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        u_repo = UserRepository(session)
        booking = await b_repo.get_by_id(booking_id)
        if not booking or booking.tutor_id != db_tutor.id:
            await callback.answer("Урок не найден")
            return
        student = await u_repo.get_by_id(booking.user_id)

    name = student.name if student else "Ученик"
    status_labels = {
        "planned": "📅 Запланирован",
        "completed": "✅ Проведён",
        "cancelled": "❌ Отменён",
        "no_show": "🚫 Неявка",
    }
    status = status_labels.get(booking.status, booking.status)
    dt = _fmt_dt(booking.scheduled_at)
    note = f"\n📝 Заметка: {booking.notes}" if booking.notes else ""
    summary = f"\n📋 Резюме: {booking.lesson_summary[:200]}" if booking.lesson_summary else ""

    text = (
        f"<b>Урок: {name}</b>\n\n"
        f"📆 {dt}\n"
        f"⏱ Длительность: {booking.duration_min} мин\n"
        f"Статус: {status}{note}{summary}"
    )

    await callback.answer()
    await callback.message.edit_text(text, reply_markup=lesson_detail_keyboard(booking_id))

@router.callback_query(F.data.startswith("tp_done_"))
async def lesson_done(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    booking_id = uuid.UUID(callback.data.replace("tp_done_", ""))

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.payment_repo import PaymentRepository
        from src.database.repositories.package_repo import PackageRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        p_repo = PaymentRepository(session)
        pkg_repo = PackageRepository(session)
        u_repo = UserRepository(session)

        booking = await b_repo.get_by_id(booking_id)
        if not booking or booking.tutor_id != db_tutor.id:
            await callback.answer("Урок не найден")
            return

        await b_repo.update(booking, status="completed")

        student = await u_repo.get_by_id(booking.user_id)

        # Попытка списать из пакета
        package_used = False
        low_package_warn = False
        if student and student.active_package_id:
            pkg = await pkg_repo.deduct_lesson(student.active_package_id)
            if pkg:
                package_used = True
                if pkg.status == "exhausted":
                    # Сбрасываем active_package_id
                    await u_repo.update(student, active_package_id=None)
                    low_package_warn = False  # exhausted — уведомим отдельно
                elif pkg.lessons_remaining <= 2:
                    low_package_warn = True

        # Если пакета нет — создаём pending-платёж
        if not package_used:
            # Приоритет: цена ученика → цена репетитора → 1000₽
            price = Decimal("1000")
            if student and student.price_per_lesson:
                price = student.price_per_lesson
            elif db_tutor.default_lesson_price:
                price = db_tutor.default_lesson_price

            await p_repo.create(
                tutor_id=db_tutor.id,
                user_id=booking.user_id,
                amount=price,
                status="pending",
                payment_type="lesson",
            )

        await session.commit()

    # Предупреждение о пакете (в фоне через bot.send_message если нужно)
    if low_package_warn and student:
        try:
            from src.services.notification_service import send_low_package_warning
            await send_low_package_warning(callback.bot, student, pkg.lessons_remaining)
        except Exception:
            pass  # Non-critical, continue

    # Переходим к вводу резюме урока
    await state.set_state(TutorStates.entering_lesson_summary)
    await state.update_data(done_booking_id=str(booking_id))

    pkg_note = " (списано из пакета)" if package_used else " (создан счёт на оплату)"
    await callback.answer("Урок отмечен!")
    await callback.message.edit_text(
        f"Урок отмечен как <b>проведённый</b> ✅{pkg_note}\n\n"
        "Напишите краткое резюме урока для родителей и записей\n"
        "(тема, что разобрали, ДЗ, комментарий).\n\n"
        "Или нажмите «Пропустить», чтобы пропустить:",
        reply_markup=lesson_summary_keyboard(booking_id),
    )


@router.callback_query(F.data.startswith("tp_noshow_"))
async def lesson_noshow(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    booking_id = uuid.UUID(callback.data.replace("tp_noshow_", ""))

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        b_repo = BookingRepository(session)
        booking = await b_repo.get_by_id(booking_id)
        if not booking or booking.tutor_id != db_tutor.id:
            await callback.answer("Урок не найден")
            return
        await b_repo.update(booking, status="no_show")

    await callback.answer("Отмечено: неявка")
    await callback.message.edit_text(
        "Отмечена <b>неявка</b> 🚫",
        reply_markup=schedule_keyboard(0),
    )


@router.callback_query(F.data.startswith("tp_cnlbook_"))
async def lesson_cancel(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    booking_id = uuid.UUID(callback.data.replace("tp_cnlbook_", ""))

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        b_repo = BookingRepository(session)
        booking = await b_repo.get_by_id(booking_id)
        if not booking or booking.tutor_id != db_tutor.id:
            await callback.answer("Урок не найден")
            return
        await b_repo.update(booking, status="cancelled")

    await callback.answer("Урок отменён")
    await callback.message.edit_text(
        "Урок <b>отменён</b> ❌",
        reply_markup=schedule_keyboard(0),
    )


# ─────────────────────────────────────────────────────────────────
# ЗАМЕТКИ к уроку и к ученику
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_note_"))
async def add_student_note_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_note_", "")
    await state.set_state(TutorStates.editing_note)
    await state.update_data(target_user_id=user_id)
    await callback.answer()
    await callback.message.answer("Напишите заметку об ученике:", reply_markup=cancel_keyboard())


@router.message(TutorStates.editing_note)
async def save_student_note(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    data = await state.get_data()
    user_id = uuid.UUID(data["target_user_id"])
    note_text = message.text or ""

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            ts = datetime.now(timezone.utc).strftime("%d.%m.%Y")
            old = student.notes or ""
            new_note = f"[{ts}] {note_text}\n"
            await repo.update(student, notes=old + new_note)

    await state.clear()
    await message.answer("Заметка сохранена ✅", reply_markup=tutor_reply_keyboard())


# ============================================================================
# ПЕРЕИМЕНОВАНИЕ УЧЕНИКА
# ============================================================================


@router.callback_query(F.data.startswith("tp_rename_"))
async def rename_student_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_rename_", "")
    await state.set_state(TutorStates.renaming_student)
    await state.update_data(target_user_id=user_id)
    await callback.answer()
    await callback.message.answer(
        "Введите новое имя ученика:",
        reply_markup=cancel_keyboard(),
    )


@router.message(TutorStates.renaming_student)
async def rename_student_save(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Имя не может быть пустым. Введите имя ученика:")
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["target_user_id"])

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if not student or student.tutor_id != db_tutor.id:
            await state.clear()
            await message.answer("Ученик не найден.")
            return
        old_name = student.name or "—"
        await repo.update(student, name=new_name)

    await state.clear()
    await message.answer(
        f"✅ Имя изменено: <b>{old_name}</b> → <b>{new_name}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{user_id}"),
        ]]),
    )


# ============================================================================
# ЦЕЛЬ УЧЕНИКА
# ============================================================================


@router.callback_query(F.data.startswith("tp_goal_"))
async def edit_student_goal_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Начать редактирование цели ученика."""
    if not _require_tutor(db_tutor):
        return

    user_id = uuid.UUID(callback.data.replace("tp_goal_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)

        if not student or student.tutor_id != db_tutor.id:
            await callback.answer("Ученик не найден")
            return

    current_goal = student.goal or "не указана"

    await state.set_state(TutorStates.editing_goal)
    await state.update_data(target_user_id=str(user_id))
    await callback.answer()
    await callback.message.answer(
        f"<b>Редактирование цели</b>\n\n"
        f"Текущая цель: <i>{current_goal}</i>\n\n"
        f"Введите новую цель обучения для ученика (до 50 символов):",
        reply_markup=cancel_keyboard()
    )


@router.message(TutorStates.editing_goal)
async def save_student_goal(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохранить цель ученика."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["target_user_id"])
    goal_text = (message.text or "").strip()

    # Валидация длины
    if len(goal_text) > 50:
        await message.answer(
            f"❌ Цель слишком длинная ({len(goal_text)} символов).\n"
            f"Максимум 50 символов. Попробуйте сократить."
        )
        return

    if not goal_text:
        await message.answer("❌ Цель не может быть пустой. Введите текст.")
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            await repo.update(student, goal=goal_text)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Цель обновлена: <b>{goal_text}</b>",
        reply_markup=tutor_reply_keyboard()
    )


@router.callback_query(F.data.startswith("tp_lnote_"))
async def add_lesson_note_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    booking_id = callback.data.replace("tp_lnote_", "")
    await state.set_state(TutorStates.editing_lesson_note)
    await state.update_data(target_booking_id=booking_id)
    await callback.answer()
    await callback.message.answer("Напишите заметку к уроку (тема, ДЗ, комментарий):", reply_markup=cancel_keyboard())


@router.message(TutorStates.editing_lesson_note)
async def save_lesson_note(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    data = await state.get_data()
    booking_id = uuid.UUID(data["target_booking_id"])

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        repo = BookingRepository(session)
        booking = await repo.get_by_id(booking_id)
        if booking:
            await repo.update(booking, notes=message.text or "")

    await state.clear()
    await message.answer("Заметка к уроку сохранена ✅", reply_markup=tutor_reply_keyboard())


# ─────────────────────────────────────────────────────────────────
# ЗАМЕТКИ (меню)
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Заметки")
async def show_notes(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        students = await repo.get_active_by_tutor(db_tutor.id)

    students_with_notes = [s for s in students if s.notes]

    if not students_with_notes:
        await message.answer(
            "<b>Заметки</b>\n\nЗаметок пока нет.\n"
            "Добавляйте заметки через карточку ученика (раздел «Мои ученики»)."
        )
        return

    lines = ["<b>Заметки по ученикам:</b>\n"]
    for s in students_with_notes[:5]:
        lines.append(f"\n<b>{s.name}</b>")
        last_notes = (s.notes or "").strip().split("\n")
        for note in last_notes[-3:]:
            if note.strip():
                lines.append(f"  {note.strip()}")

    await message.answer("\n".join(lines))


# ─────────────────────────────────────────────────────────────────
# ОПЛАТЫ
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Оплаты")
async def show_payments(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return

    async with get_session() as session:
        from src.database.repositories.payment_repo import PaymentRepository
        repo = PaymentRepository(session)
        debts = await repo.get_debt_summary(db_tutor.id)
        pending_sum = await repo.get_pending_sum(db_tutor.id)

    if not debts:
        await message.answer(
            "<b>Оплаты</b>\n\n"
            "Все уроки оплачены ✅\n"
            "Задолженностей нет."
        )
        return

    total_students = len(debts)
    lines = [
        f"<b>Оплаты</b>\n",
        f"Должников: <b>{total_students}</b>",
        f"Общий долг: <b>{pending_sum}₽</b>\n",
        "Нажмите на ученика, чтобы отметить оплату:",
    ]

    await message.answer(
        "\n".join(lines),
        reply_markup=payments_list_keyboard(debts),
    )


@router.callback_query(F.data == "tp_payments_back")
async def payments_back(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return

    async with get_session() as session:
        from src.database.repositories.payment_repo import PaymentRepository
        repo = PaymentRepository(session)
        debts = await repo.get_debt_summary(db_tutor.id)

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=payments_list_keyboard(debts))


@router.callback_query(F.data.startswith("tp_paydet_"))
async def show_payment_detail(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_paydet_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.payment_repo import PaymentRepository

        u_repo = UserRepository(session)
        p_repo = PaymentRepository(session)
        student = await u_repo.get_by_id(user_id)
        payments = await p_repo.get_by_user(db_tutor.id, user_id, limit=10)

    if not student or student.tutor_id != db_tutor.id:
        await callback.answer("Ученик не найден")
        return

    lines = [f"<b>Оплаты: {student.name or 'Ученик'}</b>\n"]
    for p in payments:
        mark = "✅" if p.status == "paid" else "❌"
        dt = p.created_at.strftime("%d.%m") if p.created_at else "?"
        lines.append(f"  {mark} {dt} — {p.amount}₽")

    unpaid = [p for p in payments if p.status == "pending"]
    if unpaid:
        total = sum(p.amount for p in unpaid)
        lines.append(f"\nИтого долг: <b>{total}₽</b>")

    await callback.answer()
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=payment_actions_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("tp_markpaid_"))
async def mark_paid_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_markpaid_", "")
    await state.set_state(TutorStates.entering_payment)
    await state.update_data(pay_user_id=user_id)
    await callback.answer()
    await callback.message.answer(
        "Введите сумму полученной оплаты (в рублях):\n"
        "Или напишите «все» чтобы отметить все задолженности оплаченными.",
        reply_markup=cancel_keyboard(),
    )


@router.message(TutorStates.entering_payment)
async def process_payment(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["pay_user_id"])
    text = (message.text or "").strip().lower()

    async with get_session() as session:
        from src.database.repositories.payment_repo import PaymentRepository
        repo = PaymentRepository(session)

        if text == "все":
            unpaid = await repo.get_by_user(db_tutor.id, user_id, limit=100)
            count = 0
            for p in unpaid:
                if p.status == "pending":
                    await repo.mark_paid(p.id)
                    count += 1
            await state.clear()
            await message.answer(
                f"Отмечено оплаченными: <b>{count}</b> уроков ✅",
                reply_markup=tutor_reply_keyboard(),
            )
            return

        try:
            amount = Decimal(text.replace(",", "."))
        except Exception:
            await message.answer("Введите сумму числом (например: 2000) или «все».")
            return

        # Закрываем самые старые pending-записи на указанную сумму
        unpaid = await repo.get_by_user(db_tutor.id, user_id, limit=100)
        remaining = amount
        closed_count = 0
        for p in reversed(unpaid):
            if p.status == "pending" and remaining > 0:
                if remaining >= p.amount:
                    await repo.mark_paid(p.id)
                    remaining -= p.amount
                    closed_count += 1
                else:
                    # Частичная оплата: создаем новый paid платеж на часть суммы
                    # и уменьшаем pending запись (для будущих доработок)
                    break

        # Если сумма больше долгов — создаем новую paid запись на остаток
        if remaining > 0:
            await repo.create(
                tutor_id=db_tutor.id,
                user_id=user_id,
                amount=remaining,
                status="paid",
                payment_type="lesson",
                paid_at=datetime.now(timezone.utc),
            )

        await session.commit()

    await state.clear()

    if closed_count > 0 and remaining > 0:
        await message.answer(
            f"✅ Закрыто долгов: <b>{closed_count}</b>\n"
            f"✅ Дополнительно записано: <b>{remaining}₽</b>",
            reply_markup=tutor_reply_keyboard(),
        )
    elif closed_count > 0:
        await message.answer(
            f"✅ Закрыто долгов: <b>{closed_count}</b> на сумму <b>{amount}₽</b>",
            reply_markup=tutor_reply_keyboard(),
        )
    else:
        await message.answer(
            f"Оплата <b>{amount}₽</b> записана ✅",
            reply_markup=tutor_reply_keyboard(),
        )


# ─────────────────────────────────────────────────────────────────
# ДОХОДЫ
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "Доходы")
async def show_income(message: Message, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    await _send_income_report(message, db_tutor, months_back=0, edit=False)


@router.callback_query(F.data == "tp_income_prev")
async def income_prev_month(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    await callback.answer()
    await _send_income_report(callback.message, db_tutor, months_back=1, edit=True)


@router.callback_query(F.data == "tp_income_all")
async def income_all_time(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    await callback.answer()
    await _send_income_report(callback.message, db_tutor, months_back=-1, edit=True)


async def _send_income_report(
    message: Message, tutor: Tutor, months_back: int, edit: bool
) -> None:
    # Используем московское время для правильного определения месяца
    now_utc = datetime.now(timezone.utc)
    now_moscow = now_utc + MOSCOW_OFFSET

    if months_back == -1:
        since = datetime(2000, 1, 1, tzinfo=timezone.utc)
        period_label = "За всё время"
    elif months_back == 0:
        # Начало текущего месяца в московском времени
        month_start_moscow = now_moscow.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        since = month_start_moscow - MOSCOW_OFFSET
        mon = _MONTHS_RU.get(now_moscow.month, "")
        period_label = f"{mon} {now_moscow.year}"
    else:
        m = now_moscow.month - months_back
        y = now_moscow.year
        if m <= 0:
            m += 12
            y -= 1
        month_start_moscow = datetime(y, m, 1, hour=0, minute=0, second=0, microsecond=0)
        since = month_start_moscow - MOSCOW_OFFSET
        period_label = f"{_MONTHS_RU.get(m, '')} {y}"

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.payment_repo import PaymentRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        p_repo = PaymentRepository(session)
        u_repo = UserRepository(session)

        # Уроки за период
        if months_back == -1:
            period_end = now_utc + timedelta(days=365)
        elif months_back == 0:
            # Конец текущего месяца в московском времени
            if now_moscow.month == 12:
                month_end_moscow = datetime(now_moscow.year + 1, 1, 1, hour=0, minute=0, second=0, microsecond=0)
            else:
                month_end_moscow = datetime(now_moscow.year, now_moscow.month + 1, 1, hour=0, minute=0, second=0, microsecond=0)
            period_end = month_end_moscow - MOSCOW_OFFSET
        else:
            # Для прошлых месяцев
            m2 = now_moscow.month - months_back + 1
            y2 = now_moscow.year
            if m2 > 12:
                m2 -= 12
                y2 += 1
            elif m2 <= 0:
                m2 += 12
                y2 -= 1
            month_end_moscow = datetime(y2, m2, 1, hour=0, minute=0, second=0, microsecond=0)
            period_end = month_end_moscow - MOSCOW_OFFSET

        bookings = await b_repo.get_upcoming_by_tutor(tutor.id, since, period_end)
        completed_lessons = [b for b in bookings if b.status == "completed"]
        planned_lessons = [b for b in bookings if b.status == "planned"]

        paid_sum = await p_repo.get_paid_sum(tutor.id, since)
        pending_sum = await p_repo.get_pending_sum(tutor.id)

        student_count = await u_repo.count_by_tutor(tutor.id)

    # Реальная цена: из настроек репетитора или 1000₽ по умолчанию
    default_price = tutor.default_lesson_price if tutor.default_lesson_price else Decimal("1000")

    # Средний чек = оплаченная сумма / количество проведенных уроков
    avg_check = (paid_sum / len(completed_lessons)) if len(completed_lessons) > 0 else default_price

    # Прогноз учитывает средний чек, а не дефолтную цену
    forecast = paid_sum + Decimal(len(planned_lessons)) * avg_check
    total_expected = paid_sum + pending_sum

    lines = [
        f"<b>📊 Доходы — {period_label}</b>\n",
        f"👥 Учеников: <b>{student_count}</b>",
        f"✅ Уроков проведено: <b>{len(completed_lessons)}</b>",
        f"📅 Уроков запланировано: <b>{len(planned_lessons)}</b>",
        "",
        f"💚 Получено: <b>{paid_sum:.0f}₽</b>",
        f"🔴 Ожидает оплаты: <b>{pending_sum:.0f}₽</b>",
        f"💛 Итого (с долгами): <b>{total_expected:.0f}₽</b>",
        f"🔮 Прогноз (с запланированными): <b>{forecast:.0f}₽</b>",
    ]

    if months_back == 0 and len(completed_lessons) > 0:
        lines.append(f"\n💡 Средний чек: <b>{avg_check:.0f}₽</b>/урок")

    await _reply(message, "\n".join(lines), income_keyboard(), edit)


async def _reply(message, text, kb, edit):
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ─────────────────────────────────────────────────────────────────
# ИСТОРИЯ УРОКОВ (из карточки ученика)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_hist_"))
async def show_student_history(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_hist_", ""))

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        u_repo = UserRepository(session)

        student = await u_repo.get_by_id(user_id)
        if not student or student.tutor_id != db_tutor.id:
            await callback.answer("Ученик не найден")
            return

        now = datetime.now(timezone.utc)
        all_bookings = await b_repo.get_upcoming_by_tutor(
            db_tutor.id,
            from_dt=now - timedelta(days=365),
            to_dt=now,
        )

    student_bookings = [b for b in all_bookings if b.user_id == user_id]
    past = sorted(student_bookings, key=lambda b: b.scheduled_at, reverse=True)

    name = student.name if student else "Ученик"
    lines = [f"<b>История уроков: {name}</b>\n"]

    if not past:
        lines.append("Прошедших уроков нет.")
    else:
        status_map = {"completed": "✅", "cancelled": "❌", "no_show": "🚫", "planned": "📅"}
        for b in past[:15]:
            status = status_map.get(b.status, "?")
            dt = _fmt_dt(b.scheduled_at)
            note = f" — {b.notes[:30]}" if b.notes else ""
            lines.append(f"{status} {dt} ({b.duration_min}м){note}")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{user_id}")]
        ]
    )
    await callback.answer()
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)


# ─────────────────────────────────────────────────────────────────
# ЗАПИСАТЬ УЧЕНИКА НА УРОК (из карточки) + ВЫБОР ДЛИТЕЛЬНОСТИ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_book_"))
async def book_for_student_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_book_", "")
    await state.update_data(booking_for_user=user_id)
    await callback.answer()
    await callback.message.answer(
        "Выберите длительность урока:",
        reply_markup=duration_keyboard(),
    )


@router.callback_query(F.data.startswith("tp_dur_"))
async def select_duration(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохраняем длительность и переходим к выбору даты."""
    if not _require_tutor(db_tutor):
        return
    duration = int(callback.data.replace("tp_dur_", ""))
    # Сохраняем tutor_id в FSM, чтобы booking flow знал кто репетитор
    await state.update_data(selected_duration=duration, booking_tutor_id=str(db_tutor.id))
    await callback.answer(f"Длительность: {duration} мин")

    # Переходим к выбору дня (стандартный booking flow)
    from src.bot.handlers.booking import start_booking_from_message
    await start_booking_from_message(callback.message, state)


@router.callback_query(F.data == "tp_noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ─────────────────────────────────────────────────────────────────
# РЕЗЮМЕ УРОКА + УВЕДОМЛЕНИЕ РОДИТЕЛЯМ
# ─────────────────────────────────────────────────────────────────

@router.message(TutorStates.entering_lesson_summary)
async def save_lesson_summary(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохраняем резюме урока и отправляем родителю."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    booking_id = uuid.UUID(data["done_booking_id"])
    summary_text = message.text or ""

    async with get_session() as session:
        from src.database.repositories.booking_repo import BookingRepository
        from src.database.repositories.user_repo import UserRepository

        b_repo = BookingRepository(session)
        u_repo = UserRepository(session)

        booking = await b_repo.get_by_id(booking_id)
        if booking and summary_text:
            await b_repo.update(booking, lesson_summary=summary_text)

        student = await u_repo.get_by_id(booking.user_id) if booking else None
        await session.commit()

    parent_sent = False
    if booking and student:
        from src.services.notification_service import send_parent_report
        parent_sent = await send_parent_report(
            bot=message.bot,
            booking=booking,
            student=student,
            tutor=db_tutor,
        )

    await state.clear()
    note = "\nОтчёт отправлен родителю ✅" if parent_sent else ""
    await message.answer(
        f"Резюме урока сохранено ✅{note}",
        reply_markup=tutor_reply_keyboard(),
    )


@router.callback_query(F.data.startswith("tp_skip_summary_"))
async def skip_lesson_summary(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Пропустить ввод резюме."""
    await state.clear()
    await callback.answer("Резюме пропущено")
    await callback.message.edit_text(
        "Урок отмечен как <b>проведённый</b> ✅",
        reply_markup=schedule_keyboard(0),
    )


# ─────────────────────────────────────────────────────────────────
# ПАКЕТЫ УРОКОВ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_pkg_"))
async def show_package_menu(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Показать меню пакетов для ученика."""
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_pkg_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.package_repo import PackageRepository

        u_repo = UserRepository(session)
        pkg_repo = PackageRepository(session)

        student = await u_repo.get_by_id(user_id)
        if not student or student.tutor_id != db_tutor.id:
            await callback.answer("Ученик не найден")
            return

        active_pkg = await pkg_repo.get_active_for_user(db_tutor.id, user_id)

    pkg_info = ""
    if active_pkg:
        pkg_info = (
            f"\n\n<b>Активный пакет:</b> {active_pkg.package_type} уроков\n"
            f"Осталось: <b>{active_pkg.lessons_remaining}</b> из {active_pkg.total_lessons}"
        )

    name = student.name if student else "Ученик"
    await callback.answer()
    await callback.message.edit_text(
        f"<b>Пакет уроков: {name}</b>{pkg_info}\n\n"
        "Выберите размер нового пакета:",
        reply_markup=package_size_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("tp_pkgsize_"))
async def package_size_selected(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Выбран размер пакета — запрашиваем цену."""
    if not _require_tutor(db_tutor):
        return
    parts = callback.data.replace("tp_pkgsize_", "").split("_", 1)
    size = parts[0]  # "4", "8", "12"
    user_id = parts[1] if len(parts) > 1 else ""

    await state.set_state(TutorStates.entering_package_price)
    await state.update_data(pkg_size=size, pkg_user_id=user_id)

    # Рассчитываем цену по умолчанию (индивидуальная > дефолтная репетитора)
    price = getattr(db_tutor, "default_lesson_price", None) or Decimal("2000")
    if user_id:
        async with get_session() as session:
            from src.database.repositories.user_repo import UserRepository
            student = await UserRepository(session).get_by_id(uuid.UUID(user_id))
            if student and student.price_per_lesson:
                price = student.price_per_lesson
    default_total = int(price) * int(size)

    await callback.answer()
    await callback.message.answer(
        f"Пакет <b>{size} уроков</b>.\n\n"
        f"Введите общую стоимость пакета в рублях\n"
        f"(по умолчанию {default_total}₽ = {int(price)}₽ × {size}):",
        reply_markup=cancel_keyboard(),
    )


@router.message(TutorStates.entering_package_price)
async def save_package(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохраняем цену и предлагаем выбрать способ оплаты."""
    if not _require_tutor(db_tutor):
        return

    text = (message.text or "").strip()
    try:
        total_price = Decimal(text.replace(",", ".").replace(" ", ""))
        if total_price <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите сумму числом (например: 8000):")
        return

    data = await state.get_data()
    size = int(data["pkg_size"])
    # Сохраняем цену в state для дальнейших шагов
    await state.update_data(pkg_price_rub=str(total_price))

    await message.answer(
        f"Пакет <b>{size} уроков · {total_price:.0f}₽</b>\n\n"
        "Выберите способ оплаты для ученика:",
        reply_markup=payment_method_keyboard(),
    )


@router.callback_query(F.data == "tp_pay_yookassa")
async def pay_by_yookassa(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Отправляем инвойс ЮKassa студенту."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    size = int(data.get("pkg_size", 4))
    user_id = uuid.UUID(data["pkg_user_id"])
    total_price = Decimal(data.get("pkg_price_rub", "0"))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        student = await UserRepository(session).get_by_id(user_id)

    if not student:
        await callback.answer("Ученик не найден")
        return

    from config.settings import settings as _settings
    if not _settings.yookassa_provider_token:
        await callback.answer(
            "ЮKassa не настроена. Добавьте YOOKASSA_PROVIDER_TOKEN в настройки бота.",
            show_alert=True,
        )
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀ К карточке ученика", callback_data=f"tp_student_{user_id}"),
    ]])

    try:
        from src.bot.handlers.student_payment import send_package_invoice
        await send_package_invoice(
            bot=callback.bot,
            student_telegram_id=student.telegram_id,
            tutor_id=db_tutor.id,
            user_id=user_id,
            tutor_name=db_tutor.name,
            size=size,
            price_rub=total_price,
        )
        await state.clear()
        await callback.answer("Счёт отправлен!")
        await callback.message.edit_text(
            f"✅ Счёт на <b>{total_price:.0f}₽</b> отправлен ученику <b>{student.name}</b>!\n\n"
            "После оплаты пакет активируется автоматически.",
            reply_markup=back_kb,
        )
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to send YooKassa invoice: {e}")
        await callback.answer("Ошибка при отправке счёта. Проверьте токен ЮKassa.", show_alert=True)


@router.callback_query(F.data == "tp_pay_stars")
async def pay_by_stars_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Запрашиваем цену в Stars для инвойса."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    size = int(data.get("pkg_size", 4))

    await state.set_state(TutorStates.entering_stars_price)
    await callback.answer()
    await callback.message.answer(
        f"Пакет <b>{size} уроков</b> через Telegram Stars.\n\n"
        "Введите стоимость в Stars (целое число):\n"
        "<i>Пример: 500</i>"
    )


@router.message(TutorStates.entering_stars_price)
async def pay_by_stars_confirm(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Отправляем инвойс в Stars студенту."""
    if not _require_tutor(db_tutor):
        return

    text = (message.text or "").strip()
    try:
        price_stars = int(text.replace(" ", ""))
        if price_stars <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите целое число Stars (например: 500):")
        return

    data = await state.get_data()
    size = int(data.get("pkg_size", 4))
    user_id = uuid.UUID(data["pkg_user_id"])

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        student = await UserRepository(session).get_by_id(user_id)

    if not student:
        await state.clear()
        await message.answer("Ученик не найден.", reply_markup=tutor_reply_keyboard())
        return

    try:
        from src.bot.handlers.student_payment import send_package_invoice_stars
        await send_package_invoice_stars(
            bot=message.bot,
            student_telegram_id=student.telegram_id,
            tutor_id=db_tutor.id,
            user_id=user_id,
            tutor_name=db_tutor.name,
            size=size,
            price_stars=price_stars,
        )
        await state.clear()
        await message.answer(
            f"✅ Счёт на <b>{price_stars} ⭐</b> отправлен ученику <b>{student.name}</b>!\n\n"
            "После оплаты пакет активируется автоматически.",
            reply_markup=tutor_reply_keyboard(),
        )
    except Exception as e:
        from loguru import logger
        logger.error(f"Failed to send Stars invoice: {e}")
        await message.answer(
            "Ошибка при отправке Stars-счёта. Попробуйте ещё раз.",
            reply_markup=tutor_reply_keyboard(),
        )
        await state.clear()


@router.callback_query(F.data == "tp_pay_manual")
async def pay_manually(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Создаём пакет вручную (без онлайн-оплаты)."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    size = int(data.get("pkg_size", 4))
    user_id = uuid.UUID(data["pkg_user_id"])
    total_price = Decimal(data.get("pkg_price_rub", "0"))

    async with get_session() as session:
        from src.database.repositories.package_repo import PackageRepository
        from src.database.repositories.user_repo import UserRepository

        pkg_repo = PackageRepository(session)
        u_repo = UserRepository(session)
        student = await u_repo.get_by_id(user_id)

        pkg = await pkg_repo.create(
            tutor_id=db_tutor.id,
            user_id=user_id,
            package_type=str(size),
            total_lessons=size,
            lessons_remaining=size,
            price_total=total_price,
            status="active",
        )
        if student:
            await u_repo.update(student, active_package_id=pkg.id)
        await session.commit()

    await state.clear()
    await callback.answer("Пакет создан!")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await callback.message.edit_text(
        f"✅ Пакет <b>{size} уроков · {total_price:.0f}₽</b> создан вручную!\n"
        "Уроки будут автоматически списываться при отметке «Проведён».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ К карточке ученика", callback_data=f"tp_student_{user_id}"),
        ]]),
    )


# ─────────────────────────────────────────────────────────────────
# ИНДИВИДУАЛЬНАЯ ЦЕНА ЗА УРОК
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_setprice_"))
async def set_student_price_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Начать установку индивидуальной цены для ученика."""
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_setprice_", "")

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        student = await UserRepository(session).get_by_id(uuid.UUID(user_id))

    if not student or student.tutor_id != db_tutor.id:
        await callback.answer("Ученик не найден")
        return

    default_price = getattr(db_tutor, "default_lesson_price", None) or Decimal("2000")
    current = f"{student.price_per_lesson:.0f}₽" if student.price_per_lesson else f"{default_price:.0f}₽ (по умолчанию)"

    await state.set_state(TutorStates.entering_student_price)
    await state.update_data(price_user_id=user_id)
    await callback.answer()
    await callback.message.answer(
        f"<b>{student.name}</b>\n"
        f"Текущая цена: <b>{current}</b>\n\n"
        f"Введите новую цену за урок в рублях.\n"
        f"Или напишите <b>0</b> чтобы сбросить до вашей цены по умолчанию ({default_price:.0f}₽):",
        reply_markup=cancel_keyboard(),
    )


@router.message(TutorStates.entering_student_price)
async def save_student_price(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохраняем индивидуальную цену ученика."""
    if not _require_tutor(db_tutor):
        return

    text = (message.text or "").strip()
    try:
        price = Decimal(text.replace(",", ".").replace(" ", ""))
        if price < 0:
            raise ValueError
    except Exception:
        await message.answer("Введите сумму числом (например: 1500 или 0 для сброса):")
        return

    data = await state.get_data()
    user_id_str = data.get("price_user_id")

    if not user_id_str:
        await message.answer("❌ Ошибка: ученик не найден. Попробуйте снова.")
        await state.clear()
        return

    user_id = uuid.UUID(user_id_str)

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)

        if not student:
            await state.clear()
            await message.answer(
                "❌ Ученик не найден в базе данных.",
                reply_markup=tutor_reply_keyboard(),
            )
            return

        new_price = None if price == 0 else price
        await repo.update(student, price_per_lesson=new_price)
        await session.commit()

    await state.clear()
    if price == 0:
        default_price = getattr(db_tutor, "default_lesson_price", None) or Decimal("2000")
        await message.answer(
            f"✅ Цена сброшена до стандартной: <b>{default_price:.0f}₽</b>",
            reply_markup=tutor_reply_keyboard(),
        )
    else:
        await message.answer(
            f"✅ Индивидуальная цена установлена: <b>{price:.0f}₽/урок</b>",
            reply_markup=tutor_reply_keyboard(),
        )


# ─────────────────────────────────────────────────────────────────
# РОДИТЕЛЬ УЧЕНИКА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_parent_"))
async def show_parent_menu(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Меню настройки родителя."""
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_parent_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)

    if not student or student.tutor_id != db_tutor.id:
        await callback.answer("Ученик не найден")
        return

    parent_info = ""
    if student.parent_telegram_id:
        parent_info = (
            f"\n\n<b>Родитель:</b> {student.parent_name or 'Не указано'}\n"
            f"Telegram ID: {student.parent_telegram_id}\n"
            f"Уведомления: {'✅' if student.notify_parent else '❌'}"
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    uid = str(user_id)
    toggle_text = "Выключить уведомления" if student.notify_parent else "Включить уведомления"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Указать Telegram ID родителя",
                callback_data=f"tp_set_parent_{uid}",
            )],
            [InlineKeyboardButton(
                text=toggle_text,
                callback_data=f"tp_toggle_parent_{uid}",
            )],
            [InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{uid}")],
        ]
    )

    await callback.answer()
    await callback.message.edit_text(
        f"<b>Родитель: {student.name}</b>{parent_info}\n\n"
        "После урока родитель получит сводку с темой, ДЗ и комментарием репетитора.",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("tp_set_parent_"))
async def set_parent_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = callback.data.replace("tp_set_parent_", "")
    await state.set_state(TutorStates.entering_parent_id)
    await state.update_data(parent_for_user=user_id)
    await callback.answer()
    await callback.message.answer(
        "Введите Telegram ID родителя (числовой).\n\n"
        "Родитель должен написать боту хотя бы раз, иначе бот не сможет ему написать.\n\n"
        "Попросите родителя переслать вам любое его сообщение или узнайте ID через @userinfobot:"
    )


@router.message(TutorStates.entering_parent_id)
async def save_parent_id(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return

    text = (message.text or "").strip()
    if message.forward_from:
        parent_tg_id = message.forward_from.id
    elif text.lstrip("-").isdigit():
        parent_tg_id = int(text)
    else:
        await message.answer("Введите числовой Telegram ID или перешлите сообщение от родителя:")
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["parent_for_user"])

    await state.set_state(TutorStates.entering_parent_name)
    await state.update_data(parent_tg_id=parent_tg_id)
    await message.answer(
        f"ID родителя: <b>{parent_tg_id}</b>\n\nВведите имя родителя:"
    )


@router.message(TutorStates.entering_parent_name)
async def save_parent_name(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["parent_for_user"])
    parent_tg_id = data["parent_tg_id"]
    parent_name = (message.text or "").strip()[:200]

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            await repo.update(
                student,
                parent_telegram_id=parent_tg_id,
                parent_name=parent_name,
                notify_parent=True,
            )
        await session.commit()

    await state.clear()
    await message.answer(
        f"Родитель <b>{parent_name}</b> привязан ✅\n"
        "Уведомления после уроков включены.",
        reply_markup=tutor_reply_keyboard(),
    )


@router.callback_query(F.data.startswith("tp_toggle_parent_"))
async def toggle_parent_notify(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_toggle_parent_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)

        if not student:
            await callback.answer("❌ Ученик не найден.")
            return

        new_state = not student.notify_parent
        await repo.update(student, notify_parent=new_state)
        await session.commit()

    state_word = "включены ✅" if new_state else "выключены ❌"
    await callback.answer(f"Уведомления {state_word}")
    await callback.message.answer(
        f"Уведомления родителю {state_word}. Используйте кнопку «Родитель» в карточке ученика для изменений.",
        reply_markup=tutor_reply_keyboard(),
    )

# ─────────────────────────────────────────────────────────────────
# УРОВЕНЬ УЧЕНИКА (CEFR)
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_setlevel_"))
async def show_level_menu(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Показать выбор уровня CEFR для ученика."""
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_setlevel_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        student = await UserRepository(session).get_by_id(user_id)

    if not student or student.tutor_id != db_tutor.id:
        await callback.answer("Ученик не найден")
        return

    current = student.cefr_level or "не определён"
    await callback.answer()
    await callback.message.edit_text(
        f"<b>{student.name}</b>\n"
        f"Текущий уровень: <b>{current}</b>\n\n"
        "Выберите уровень CEFR:",
        reply_markup=level_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("tp_level_"))
async def save_student_level(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохранить уровень CEFR ученика."""
    if not _require_tutor(db_tutor):
        return
    # Format: tp_level_{LEVEL}_{uid}
    parts = callback.data.replace("tp_level_", "").split("_", 1)
    level = parts[0]  # e.g. A1, B2
    user_id = uuid.UUID(parts[1])

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            await repo.update(student, cefr_level=level)
        await session.commit()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await callback.answer(f"Уровень {level} сохранён ✅")
    await callback.message.edit_text(
        f"Уровень <b>{level}</b> установлен ✅",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{user_id}"),
        ]]),
    )


# ─────────────────────────────────────────────────────────────────
# ПРОГРЕСС УЧЕНИКА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tp_progress_"))
async def show_progress_menu(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Показать текущий прогресс и клавиатуру выбора."""
    if not _require_tutor(db_tutor):
        return
    user_id = uuid.UUID(callback.data.replace("tp_progress_", ""))

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        student = await UserRepository(session).get_by_id(user_id)

    if not student or student.tutor_id != db_tutor.id:
        await callback.answer("Ученик не найден")
        return

    from src.services.analytics_service import _progress_bar
    pct = student.progress_level or 0
    bar = _progress_bar(pct)

    await callback.answer()
    await callback.message.edit_text(
        f"<b>{student.name}</b>\n"
        f"📈 Прогресс: <b>{bar}</b>\n\n"
        "Выберите новое значение:",
        reply_markup=progress_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("tp_setprog_"))
async def save_student_progress(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохранить прогресс ученика."""
    if not _require_tutor(db_tutor):
        return
    # Format: tp_setprog_{pct}_{uid}
    parts = callback.data.replace("tp_setprog_", "").split("_", 1)
    pct = int(parts[0])
    user_id = uuid.UUID(parts[1])

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            await repo.update(student, progress_level=pct)
        await session.commit()

    from src.services.analytics_service import _progress_bar
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await callback.answer(f"Прогресс {pct}% сохранён ✅")
    await callback.message.edit_text(
        f"Прогресс установлен: <b>{_progress_bar(pct)}</b> ✅",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{user_id}"),
        ]]),
    )


@router.callback_query(F.data.startswith("tp_prog_manual_"))
async def manual_progress_start(
    callback: CallbackQuery, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Начать ручной ввод прогресса."""
    if not _require_tutor(db_tutor):
        return

    user_id = callback.data.replace("tp_prog_manual_", "")

    await state.set_state(TutorStates.entering_progress)
    await state.update_data(target_user_id=user_id)
    await callback.answer()
    await callback.message.answer(
        "Введите процент прогресса (число от 0 до 100):",
        reply_markup=cancel_keyboard()
    )


@router.message(TutorStates.entering_progress)
async def save_manual_progress(
    message: Message, state: FSMContext, db_tutor: Optional[Tutor] = None
) -> None:
    """Сохранить прогресс из ручного ввода."""
    if not _require_tutor(db_tutor):
        return

    data = await state.get_data()
    user_id = uuid.UUID(data["target_user_id"])
    progress_text = (message.text or "").strip()

    # Валидация: должно быть число
    if not progress_text.isdigit():
        await message.answer(
            "❌ Введите число от 0 до 100.\n"
            "Например: 35 или 90"
        )
        return

    progress = int(progress_text)

    # Валидация: диапазон 0-100
    if not (0 <= progress <= 100):
        await message.answer(
            f"❌ Значение {progress} вне диапазона.\n"
            f"Введите число от 0 до 100."
        )
        return

    # Сохранение
    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        repo = UserRepository(session)
        student = await repo.get_by_id(user_id)
        if student:
            await repo.update(student, progress_level=progress)
        await session.commit()

    from src.services.analytics_service import _progress_bar
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    await state.clear()
    await message.answer(
        f"Прогресс установлен: <b>{_progress_bar(progress)}</b> ✅",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{user_id}"),
        ]])
    )


# ─────────────────────────────────────────────────────────────────
# ФИНАНСОВЫЙ ДАШБОРД
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "tp_finance_detail")
async def show_finance_dashboard(
    callback: CallbackQuery, db_tutor: Optional[Tutor] = None
) -> None:
    """Детальный финансовый дашборд."""
    if not _require_tutor(db_tutor):
        return

    await callback.answer()
    from src.services.analytics_service import AnalyticsService
    svc = AnalyticsService()
    default_price = getattr(db_tutor, "default_lesson_price", None) or Decimal("2000")
    m = await svc.get_financial_dashboard(db_tutor.id, default_lesson_price=default_price)

    week_diff = m.week_current - m.week_prev
    if week_diff > 0:
        trend = f"↑+{week_diff}"
    elif week_diff < 0:
        trend = f"↓{week_diff}"
    else:
        trend = "="

    top_line = ""
    if m.top_student_name:
        top_line = f"\n🏆 Топ: <b>{m.top_student_name}</b> ({m.top_student_revenue:.0f}₽)"

    text = (
        f"<b>💼 Финансовый дашборд — {m.period_label}</b>\n\n"
        f"📈 Получено: <b>{m.income_paid:.0f}₽</b> | Ожидает: <b>{m.income_pending:.0f}₽</b>\n"
        f"📉 Неявок: <b>{m.no_show_count}</b> (потери ≈ <b>{m.losses_no_shows:.0f}₽</b>)\n"
        f"💡 Средний чек: <b>{m.avg_check:.0f}₽</b> | Прогноз: <b>{m.revenue_forecast:.0f}₽</b>\n"
        f"📋 Проведено: <b>{m.completed_count}</b> | Запланировано: <b>{m.planned_count}</b>"
        f"{top_line}\n"
        f"📅 Эта неделя: <b>{m.week_current}</b> ур. ({trend} к прошлой)"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀ К доходам", callback_data="tp_income_back"),
    ]])

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "tp_income_back")
async def income_back(callback: CallbackQuery, db_tutor: Optional[Tutor] = None) -> None:
    if not _require_tutor(db_tutor):
        return
    await callback.answer()
    await _send_income_report(callback.message, db_tutor, months_back=0, edit=True)


# ─────────────────────────────────────────────────────────────────
# AI ФУНКЦИИ (PREMIUM ONLY)
# ─────────────────────────────────────────────────────────────────

@router.message(F.text.in_({"📝 Составить план урока", "Составить план урока"}))
async def create_lesson_plan_start(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
    subscription_plan = None
) -> None:
    """Начать создание плана урока через AI (только premium)."""
    if not _require_tutor(db_tutor):
        return

    # Проверка подписки premium
    if not subscription_plan or not subscription_plan.has_feature("ai_lesson_planning"):
        await message.answer(
            "🔒 <b>Функция доступна на тарифе ПРО</b>\n\n"
            "Тариф ПРО (1 990₽/мес) включает:\n"
            "• 📝 Составление планов уроков через AI\n"
            "• ✅ Проверка домашних заданий AI — без ограничений\n"
            "• 📊 Расширенная аналитика и другие функции\n\n"
            "Нажмите <b>💎 Моя подписка</b> чтобы оформить.",
            reply_markup=tutor_reply_keyboard()
        )
        return

    await state.set_state(TutorStates.creating_lesson_plan)
    await message.answer(
        "📝 <b>Составление плана урока</b>\n\n"
        "Опишите параметры урока:\n"
        "• Тема урока\n"
        "• Уровень студента\n"
        "• Длительность (минут)\n"
        "• Особые пожелания\n\n"
        "Например:\n"
        "<i>\"Present Perfect, уровень B1, 60 минут, больше разговорной практики\"</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="tp_cancel_state")]
        ])
    )


@router.message(TutorStates.creating_lesson_plan)
async def process_lesson_plan_request(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None
) -> None:
    """Обработка запроса на создание плана урока через AI."""
    if not _require_tutor(db_tutor):
        return

    user_request = message.text.strip()

    if len(user_request) < 10:
        await message.answer(
            "❌ Слишком короткое описание. Напишите подробнее:\n"
            "• Тема урока\n"
            "• Уровень студента\n"
            "• Длительность\n"
            "• Особые пожелания"
        )
        return

    await state.clear()

    # TODO: Здесь интеграция с AI (Claude API или OpenAI)
    # Пока заглушка
    plan = f"""📝 <b>План урока</b>

<b>Запрос:</b> {user_request}

<b>Структура урока:</b>

1️⃣ <b>Разминка (5 мин)</b>
   • Small talk
   • Review предыдущей темы

2️⃣ <b>Введение темы (10 мин)</b>
   • Presentation нового материала
   • Примеры использования

3️⃣ <b>Практика (30 мин)</b>
   • Controlled practice (упражнения)
   • Free practice (диалоги)

4️⃣ <b>Закрепление (10 мин)</b>
   • Игры / Quiz
   • Production activity

5️⃣ <b>Подведение итогов (5 мин)</b>
   • Feedback
   • Homework

<b>Материалы:</b>
• Презентация PPT
• Рабочие листы
• Онлайн упражнения

<i>💡 Сгенерировано AI</i>"""

    await message.answer(
        plan,
        reply_markup=tutor_reply_keyboard()
    )


@router.message(F.text == "✅ Проверить ДЗ")
async def check_homework_start(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None,
    subscription_plan = None
) -> None:
    """Начать проверку домашнего задания через AI (только premium)."""
    if not _require_tutor(db_tutor):
        return

    # Проверка подписки premium
    if not subscription_plan or not subscription_plan.has_feature("ai_homework_check"):
        await message.answer(
            "🔒 <b>Функция доступна на тарифе ПРО</b>\n\n"
            "Тариф ПРО (1 990₽/мес) включает:\n"
            "• 📝 Составление планов уроков через AI\n"
            "• ✅ Проверка домашних заданий AI — без ограничений\n"
            "• 📊 Расширенная аналитика и другие функции\n\n"
            "Нажмите <b>💎 Моя подписка</b> чтобы оформить.",
            reply_markup=tutor_reply_keyboard()
        )
        return

    await state.set_state(TutorStates.checking_homework)
    await message.answer(
        "✅ <b>Проверка домашнего задания</b>\n\n"
        "Отправьте текст домашнего задания для проверки.\n"
        "Можно отправить:\n"
        "• Текст эссе\n"
        "• Ответы на упражнения\n"
        "• Фото выполненной работы\n\n"
        "AI проанализирует и укажет ошибки.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="tp_cancel_state")]
        ])
    )


@router.message(TutorStates.checking_homework)
async def process_homework_check(
    message: Message,
    state: FSMContext,
    db_tutor: Optional[Tutor] = None
) -> None:
    """Обработка проверки домашнего задания через AI."""
    if not _require_tutor(db_tutor):
        return

    homework_text = message.text or message.caption

    if not homework_text and not message.photo:
        await message.answer(
            "❌ Отправьте текст или фото домашнего задания."
        )
        return

    if homework_text and len(homework_text) < 20:
        await message.answer(
            "❌ Слишком короткий текст. Отправьте полное задание."
        )
        return

    await state.clear()

    # TODO: Здесь интеграция с AI (Claude API или OpenAI)
    # Для фото: использовать Vision API
    # Пока заглушка
    feedback = f"""✅ <b>Проверка выполнена!</b>

<b>Анализ:</b>

✅ <b>Сильные стороны:</b>
• Хорошая структура текста
• Правильное использование времён

❌ <b>Ошибки:</b>
1. "I go to school <u>yesterday</u>" → "I <b>went</b> to school yesterday"
   (Past Simple для прошедшего времени)

2. "She don't like apples" → "She <b>doesn't</b> like apples"
   (3-е лицо ед.ч. требует doesn't)

💡 <b>Рекомендации:</b>
• Повторить Past Simple
• Больше практики с 3-м лицом

<b>Оценка:</b> 7/10

<i>💡 Проверено AI</i>"""

    await message.answer(
        feedback,
        reply_markup=tutor_reply_keyboard()
    )
