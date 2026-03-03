"""Админ-панель для управления всеми данными бота."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import text

from config.settings import settings
from src.bot.keyboards.admin_kb import (
    admin_main_menu,
    booking_edit_keyboard,
    cancel_admin_keyboard,
    payment_edit_keyboard,
    payments_admin_keyboard,
    schedule_admin_keyboard,
    student_edit_keyboard,
    students_admin_keyboard,
    tutor_admin_panel,
    tutors_list_keyboard,
)
from src.bot.states.admin_states import AdminStates
from src.database.engine import get_session

router = Router(name="admin_panel")

# Московское время
MOSCOW_OFFSET = timedelta(hours=3)


async def find_uuid_by_prefix(session, table: str, prefix: str, column: str = "id") -> uuid.UUID | None:
    """
    Ищет полный UUID в таблице по префиксу (первые 12 hex символов).
    """
    query = text(f"SELECT {column} FROM {table} WHERE REPLACE(CAST({column} AS TEXT), '-', '') LIKE :prefix")
    result = await session.execute(query, {"prefix": f"{prefix}%"})
    row = result.first()
    return uuid.UUID(str(row[0])) if row else None


def _require_admin(is_admin: bool) -> bool:
    """Проверка прав администратора."""
    return is_admin


async def _get_admin_user_id(message_or_callback) -> int:
    """Получить ID пользователя."""
    if hasattr(message_or_callback, "from_user"):
        return message_or_callback.from_user.id
    return 0


# ─────────────────────────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ АДМИНКИ
# ─────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_command(message: Message, is_admin: bool = False) -> None:
    """Вход в админ-панель."""
    user_id = message.from_user.id

    # Если пользователь не админ, показываем инструкцию
    if not _require_admin(is_admin):
        admin_ids = settings.get_admin_ids()

        # Если админов вообще нет, предлагаем добавить первого админа
        if not admin_ids:
            await message.answer(
                "🔐 <b>Настройка админ-панели</b>\n\n"
                f"Ваш Telegram ID: <code>{user_id}</code>\n\n"
                "Список админов пуст. Чтобы стать первым админом:\n\n"
                "1️⃣ Скопируйте ваш ID выше\n"
                "2️⃣ Подключитесь к VPS:\n"
                "<code>ssh root@94.156.131.229</code>\n\n"
                "3️⃣ Откройте файл .env:\n"
                "<code>cd /opt/repetitor-bot && nano .env</code>\n\n"
                "4️⃣ Добавьте строку (вставьте ваш ID):\n"
                f"<code>ADMIN_USER_IDS=\"{user_id}\"</code>\n\n"
                "5️⃣ Сохраните (Ctrl+O, Enter, Ctrl+X)\n\n"
                "6️⃣ Перезапустите бота:\n"
                "<code>docker compose restart bot</code>\n\n"
                "7️⃣ Отправьте /admin снова"
            )
        else:
            await message.answer(
                "❌ <b>Нет доступа к админ-панели</b>\n\n"
                f"Ваш Telegram ID: <code>{user_id}</code>\n\n"
                "Чтобы получить доступ, попросите администратора добавить ваш ID в настройки бота.\n\n"
                f"Текущие админы: {', '.join(str(aid) for aid in admin_ids)}"
            )
        return

    await message.answer(
        "🔐 <b>Админ-панель</b>\n\n"
        "Управление всеми данными бота:\n"
        "• Просмотр всех репетиторов\n"
        "• Редактирование учеников\n"
        "• Управление расписанием\n"
        "• Редактирование оплат\n"
        "• Изменение любых цифр",
        reply_markup=admin_main_menu(),
    )


@router.message(F.text == "🔙 Выход из админки")
async def exit_admin(message: Message, state: FSMContext) -> None:
    """Выход из админ-панели."""
    await state.clear()
    from src.bot.keyboards.main_menu import main_menu_keyboard
    await message.answer(
        "Выход из админ-панели.",
        reply_markup=main_menu_keyboard(),
    )


# ─────────────────────────────────────────────────────────────────
# СПИСОК РЕПЕТИТОРОВ
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Все репетиторы")
async def show_all_tutors(message: Message, is_admin: bool = False) -> None:
    """Показать список всех репетиторов."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    async with get_session() as session:
        from src.database.repositories.tutor_repo import TutorRepository
        from src.database.repositories.user_repo import UserRepository

        t_repo = TutorRepository(session)
        u_repo = UserRepository(session)

        # Получаем всех репетиторов
        tutors = await session.execute(
            text("SELECT id, telegram_id, name, default_lesson_price FROM tutors")
        )
        tutors_list = [
            {
                "id": str(row.id),
                "user_id": row.telegram_id,
                "name": row.name,
                "price": row.default_lesson_price or 0,
            }
            for row in tutors.all()
        ]

    if not tutors_list:
        await message.answer("Репетиторов пока нет.")
        return

    await message.answer(
        f"<b>Все репетиторы ({len(tutors_list)})</b>",
        reply_markup=tutors_list_keyboard(tutors_list),
    )


@router.callback_query(F.data.startswith("adm_tutors_"))
async def tutors_pagination(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Пагинация списка репетиторов."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    page = int(callback.data.replace("adm_tutors_", ""))

    async with get_session() as session:
        tutors = await session.execute(
            text("SELECT id, telegram_id, name, default_lesson_price FROM tutors")
        )
        tutors_list = [
            {
                "id": str(row.id),
                "user_id": row.telegram_id,
                "name": row.name,
                "price": row.default_lesson_price or 0,
            }
            for row in tutors.all()
        ]

    await callback.answer()
    await callback.message.edit_text(
        f"<b>Все репетиторы ({len(tutors_list)})</b>",
        reply_markup=tutors_list_keyboard(tutors_list, page=page),
    )


# ─────────────────────────────────────────────────────────────────
# ПАНЕЛЬ РЕПЕТИТОРА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_tutor_"))
async def show_tutor_panel(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Показать панель управления репетитором."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_tutor_", "")

    async with get_session() as session:
        # Находим полный UUID по короткому префиксу
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        from src.database.models import Tutor
        from sqlalchemy import select

        result = await session.execute(
            select(Tutor).where(Tutor.id == tutor_id)
        )
        tutor = result.scalar_one_or_none()

        if not tutor:
            await callback.answer("Репетитор не найден.")
            return

    await callback.answer()
    await callback.message.edit_text(
        f"<b>👤 Репетитор: {tutor.name}</b>\n\n"
        f"ID: {tutor.id}\n"
        f"Telegram ID: {tutor.telegram_id}\n"
        f"Цена урока: {tutor.default_lesson_price or 0}₽\n\n"
        "Выберите действие:",
        reply_markup=tutor_admin_panel(tutor_id),
    )


# ─────────────────────────────────────────────────────────────────
# УЧЕНИКИ РЕПЕТИТОРА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_students_"))
async def show_tutor_students(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Показать список учеников репетитора."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_students_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        from src.database.repositories.user_repo import UserRepository
        u_repo = UserRepository(session)
        students = await u_repo.get_active_by_tutor(tutor_id)

    students_list = [
        {
            "id": str(s.id),
            "name": s.name,
            "price": s.price_per_lesson or 0,
        }
        for s in students
    ]

    await callback.answer()
    await callback.message.edit_text(
        f"<b>Ученики ({len(students_list)})</b>",
        reply_markup=students_admin_keyboard(students_list, tutor_id),
    )


@router.callback_query(F.data.startswith("adm_edit_student_"))
async def edit_student(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Редактирование данных ученика."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_edit_student_", "").split("_")
    short_student_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        student_id = await find_uuid_by_prefix(session, "users", short_student_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not student_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository
        u_repo = UserRepository(session)
        student = await u_repo.get_by_id(student_id)

        if not student:
            await callback.answer("Ученик не найден.")
            return

    await callback.answer()
    await callback.message.edit_text(
        f"<b>✏️ Редактирование: {student.name}</b>\n\n"
        f"Цена урока: {student.price_per_lesson or 0}₽\n"
        f"Уровень: {student.cefr_level or '—'}\n"
        f"Прогресс: {student.progress_level or 0}%\n\n"
        "Выберите что изменить:",
        reply_markup=student_edit_keyboard(student_id, tutor_id),
    )


# ─────────────────────────────────────────────────────────────────
# ОПЛАТЫ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_payments_"))
async def show_tutor_payments(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Показать список оплат репетитора."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_payments_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        from src.database.repositories.payment_repo import PaymentRepository
        p_repo = PaymentRepository(session)

        # Получаем последние 20 платежей
        result = await session.execute(
            text("SELECT p.id, p.amount, p.status, u.name as user_name "
                 "FROM payments p JOIN users u ON p.user_id = u.id "
                 "WHERE p.tutor_id = :tutor_id "
                 "ORDER BY p.created_at DESC LIMIT 20"),
            {"tutor_id": str(tutor_id)}
        )
        payments = [
            {
                "id": str(row.id),
                "amount": row.amount,
                "status": row.status,
                "user_name": row.user_name,
            }
            for row in result.all()
        ]

    await callback.answer()
    await callback.message.edit_text(
        f"<b>💰 Оплаты ({len(payments)})</b>",
        reply_markup=payments_admin_keyboard(payments, tutor_id),
    )


@router.callback_query(F.data.startswith("adm_editpay_"))
async def edit_payment(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Редактирование платежа."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_editpay_", "").split("_")
    short_payment_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        payment_id = await find_uuid_by_prefix(session, "payments", short_payment_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not payment_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

    async with get_session() as session:
        from src.database.repositories.payment_repo import PaymentRepository
        p_repo = PaymentRepository(session)
        payment = await p_repo.get_by_id(payment_id)

        if not payment:
            await callback.answer("Платёж не найден.")
            return

    status_text = "✅ Оплачен" if payment.status == "paid" else "❌ Не оплачен"

    await callback.answer()
    await callback.message.edit_text(
        f"<b>💰 Платёж</b>\n\n"
        f"Сумма: {payment.amount}₽\n"
        f"Статус: {status_text}\n\n"
        "Выберите действие:",
        reply_markup=payment_edit_keyboard(payment_id, tutor_id),
    )


# ─────────────────────────────────────────────────────────────────
# РАСПИСАНИЕ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_schedule_"))
async def show_tutor_schedule(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Показать расписание репетитора."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_schedule_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        from src.database.repositories.booking_repo import BookingRepository
        b_repo = BookingRepository(session)

        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        week_end = now + timedelta(days=14)

        bookings_list = await b_repo.get_upcoming_by_tutor(tutor_id, week_start, week_end)

        # Получаем имена учеников
        bookings = []
        for b in bookings_list:
            result = await session.execute(
                text("SELECT name FROM users WHERE id = :user_id"),
                {"user_id": str(b.user_id)}
            )
            user_row = result.first()
            bookings.append({
                "id": str(b.id),
                "scheduled_at": b.scheduled_at,
                "status": b.status,
                "user_name": user_row.name if user_row else "?",
            })

    await callback.answer()
    await callback.message.edit_text(
        f"<b>📅 Расписание ({len(bookings)})</b>",
        reply_markup=schedule_admin_keyboard(bookings, tutor_id),
    )


@router.callback_query(F.data.startswith("adm_editbook_"))
async def edit_booking(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Редактирование урока."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_editbook_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not booking_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.repositories.booking_repo import BookingRepository
        b_repo = BookingRepository(session)
        booking = await b_repo.get_by_id(booking_id)

        if not booking:
            await callback.answer("Урок не найден.")
            return

        # Московское время
        dt_moscow = booking.scheduled_at + MOSCOW_OFFSET

    status_map = {"planned": "📅 Запланирован", "completed": "✅ Проведён", "cancelled": "❌ Отменён", "no_show": "🚫 Неявка"}
    status_text = status_map.get(booking.status, booking.status)

    await callback.answer()
    await callback.message.edit_text(
        f"<b>📅 Урок</b>\n\n"
        f"Дата: {dt_moscow.strftime('%d.%m.%Y')}\n"
        f"Время: {dt_moscow.strftime('%H:%M')}\n"
        f"Длительность: {booking.duration_min} мин\n"
        f"Статус: {status_text}\n\n"
        "Выберите действие:",
        reply_markup=booking_edit_keyboard(booking_id, tutor_id),
    )


@router.callback_query(F.data.startswith("adm_booktime_"))
async def edit_booking_time(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    """Начать изменение времени урока."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_booktime_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    await state.set_state(AdminStates.editing_booking_time)
    await state.update_data(booking_id=short_booking_id, tutor_id=short_tutor_id)

    await callback.answer()
    await callback.message.edit_text(
        "⏰ <b>Изменение времени урока</b>\n\n"
        "Отправьте новое время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Например: <code>25.02.2026 15:30</code>",
        reply_markup=cancel_admin_keyboard()
    )


@router.callback_query(F.data.startswith("adm_bookdur_"))
async def edit_booking_duration(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    """Начать изменение длительности урока."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_bookdur_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    await state.set_state(AdminStates.editing_booking_duration)
    await state.update_data(booking_id=short_booking_id, tutor_id=short_tutor_id)

    await callback.answer()
    await callback.message.edit_text(
        "⏱ <b>Изменение длительности</b>\n\n"
        "Отправьте новую длительность в минутах:\n"
        "Например: <code>60</code> или <code>90</code>",
        reply_markup=cancel_admin_keyboard()
    )


@router.callback_query(F.data.startswith("adm_bookdone_"))
async def mark_booking_completed(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Отметить урок как проведенный."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_bookdone_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not booking_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.models import Booking
        from sqlalchemy import update

        await session.execute(
            update(Booking).where(Booking.id == booking_id).values(status="completed")
        )
        await session.commit()

    await callback.answer("✅ Урок отмечен проведенным")
    # Вернемся к списку уроков
    callback.data = f"adm_schedule_{short_tutor_id}"
    await show_tutor_schedule(callback, is_admin)


@router.callback_query(F.data.startswith("adm_bookcancel_"))
async def cancel_booking(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Отменить урок."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_bookcancel_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not booking_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.models import Booking
        from sqlalchemy import update

        await session.execute(
            update(Booking).where(Booking.id == booking_id).values(status="cancelled")
        )
        await session.commit()

    await callback.answer("✅ Урок отменен")
    callback.data = f"adm_schedule_{short_tutor_id}"
    await show_tutor_schedule(callback, is_admin)


@router.callback_query(F.data.startswith("adm_delbook_"))
async def delete_booking(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Удалить урок."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_delbook_", "").split("_")
    short_booking_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not booking_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.models import Booking
        from sqlalchemy import delete

        await session.execute(
            delete(Booking).where(Booking.id == booking_id)
        )
        await session.commit()

    await callback.answer("✅ Урок удален")
    callback.data = f"adm_schedule_{short_tutor_id}"
    await show_tutor_schedule(callback, is_admin)


# Обработка нового времени урока
@router.message(AdminStates.editing_booking_time)
async def process_new_booking_time(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка нового времени урока."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_booking_id = data.get("booking_id")
    short_tutor_id = data.get("tutor_id")

    try:
        # Парсим дату в формате ДД.ММ.ГГГГ ЧЧ:ММ
        new_time = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        # Конвертируем из московского в UTC
        new_time_utc = new_time - MOSCOW_OFFSET
    except Exception:
        await message.answer("❌ Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
        return

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        if not booking_id:
            await message.answer("Урок не найден.")
            await state.clear()
            return

        from src.database.models import Booking
        from sqlalchemy import update

        await session.execute(
            update(Booking).where(Booking.id == booking_id).values(scheduled_at=new_time_utc)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Время изменено: {new_time.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=admin_main_menu()
    )


# Обработка новой длительности урока
@router.message(AdminStates.editing_booking_duration)
async def process_new_booking_duration(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка новой длительности урока."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_booking_id = data.get("booking_id")

    try:
        new_duration = int(message.text.strip())
        if new_duration <= 0 or new_duration > 300:
            await message.answer("❌ Длительность должна быть от 1 до 300 минут.")
            return
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with get_session() as session:
        booking_id = await find_uuid_by_prefix(session, "bookings", short_booking_id)
        if not booking_id:
            await message.answer("Урок не найден.")
            await state.clear()
            return

        from src.database.models import Booking
        from sqlalchemy import update

        await session.execute(
            update(Booking).where(Booking.id == booking_id).values(duration_min=new_duration)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Длительность изменена: {new_duration} мин",
        reply_markup=admin_main_menu()
    )


# ─────────────────────────────────────────────────────────────────
# РЕДАКТИРОВАНИЕ УЧЕНИКОВ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_edprice_"))
async def edit_student_price(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    """Начать изменение цены урока для ученика."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_edprice_", "").split("_")
    short_student_id = parts[0]
    short_tutor_id = parts[1]

    await state.set_state(AdminStates.editing_student_price)
    await state.update_data(student_id=short_student_id, tutor_id=short_tutor_id)

    await callback.answer()
    await callback.message.edit_text(
        "💵 <b>Изменение цены урока</b>\n\n"
        "Отправьте новую цену числом:\n"
        "Например: <code>1500</code>",
        reply_markup=cancel_admin_keyboard()
    )


@router.callback_query(F.data.startswith("adm_ednote_"))
async def edit_student_note(callback: CallbackQuery, state: FSMContext, is_admin: bool = False) -> None:
    """Начать изменение заметки ученика."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_ednote_", "").split("_")
    short_student_id = parts[0]
    short_tutor_id = parts[1]

    await state.set_state(AdminStates.editing_note)
    await state.update_data(student_id=short_student_id, tutor_id=short_tutor_id)

    await callback.answer()
    await callback.message.edit_text(
        "📝 <b>Редактирование заметки</b>\n\n"
        "Отправьте новый текст заметки:",
        reply_markup=cancel_admin_keyboard()
    )


@router.callback_query(F.data.startswith("adm_delstud_"))
async def delete_student(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Удалить ученика (деактивировать)."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_delstud_", "").split("_")
    short_student_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        student_id = await find_uuid_by_prefix(session, "users", short_student_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not student_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.models import User
        from sqlalchemy import update

        await session.execute(
            update(User).where(User.id == student_id).values(is_active=False)
        )
        await session.commit()

    await callback.answer("✅ Ученик деактивирован")
    callback.data = f"adm_students_{short_tutor_id}"
    await show_tutor_students(callback, is_admin)


# Обработка новой цены ученика
@router.message(AdminStates.editing_student_price)
async def process_new_student_price(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка новой цены ученика."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_student_id = data.get("student_id")

    try:
        new_price = Decimal(message.text.strip())
        if new_price <= 0:
            await message.answer("❌ Цена должна быть больше нуля.")
            return
    except Exception:
        await message.answer("❌ Введите число.")
        return

    async with get_session() as session:
        student_id = await find_uuid_by_prefix(session, "users", short_student_id)
        if not student_id:
            await message.answer("Ученик не найден.")
            await state.clear()
            return

        from src.database.models import User
        from sqlalchemy import update

        await session.execute(
            update(User).where(User.id == student_id).values(price_per_lesson=new_price)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Цена обновлена: {new_price}₽",
        reply_markup=admin_main_menu()
    )


# Обработка новой заметки
@router.message(AdminStates.editing_note)
async def process_new_note(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка новой заметки."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_student_id = data.get("student_id")
    new_note = message.text.strip()

    async with get_session() as session:
        student_id = await find_uuid_by_prefix(session, "users", short_student_id)
        if not student_id:
            await message.answer("Ученик не найден.")
            await state.clear()
            return

        from src.database.models import User
        from sqlalchemy import update

        await session.execute(
            update(User).where(User.id == student_id).values(notes=new_note)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ Заметка обновлена",
        reply_markup=admin_main_menu()
    )


# ─────────────────────────────────────────────────────────────────
# ДЕЙСТВИЯ С ДАННЫМИ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_cancel")
async def cancel_admin_action(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена текущего действия."""
    await state.clear()
    await callback.answer("Действие отменено.")
    await callback.message.answer("Действие отменено.", reply_markup=admin_main_menu())


# ─────────────────────────────────────────────────────────────────
# ИЗМЕНЕНИЕ СУММЫ ПЛАТЕЖА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_payamt_"))
async def start_edit_payment_amount(
    callback: CallbackQuery, state: FSMContext, is_admin: bool = False
) -> None:
    """Начать изменение суммы платежа."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_payamt_", "").split("_")
    payment_id = parts[0]
    tutor_id = parts[1]

    await state.set_state(AdminStates.editing_payment_amount)
    await state.update_data(payment_id=payment_id, tutor_id=tutor_id)

    await callback.answer()
    await callback.message.edit_text(
        "Введите новую сумму платежа (в рублях):",
        reply_markup=cancel_admin_keyboard(),
    )


@router.message(AdminStates.editing_payment_amount)
async def save_payment_amount(
    message: Message, state: FSMContext, is_admin: bool = False
) -> None:
    """Сохранить новую сумму платежа."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0.")
            return
    except Exception:
        await message.answer("❌ Введите корректное число.")
        return

    data = await state.get_data()
    short_payment_id = data["payment_id"]
    short_tutor_id = data["tutor_id"]

    async with get_session() as session:
        # Восстанавливаем полные UUID из коротких ID
        payment_id = await find_uuid_by_prefix(session, "payments", short_payment_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)

        if not payment_id or not tutor_id:
            await state.clear()
            await message.answer("❌ Платеж не найден.", reply_markup=admin_main_menu())
            return

        from src.database.repositories.payment_repo import PaymentRepository
        p_repo = PaymentRepository(session)
        payment = await p_repo.get_by_id(payment_id)

        if payment:
            payment.amount = amount
            await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Сумма платежа изменена на {amount}₽",
        reply_markup=admin_main_menu(),
    )


# ─────────────────────────────────────────────────────────────────
# ОТМЕТИТЬ ПЛАТЕЖ ОПЛАЧЕННЫМ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_paypaid_"))
async def mark_payment_paid(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Отметить платёж оплаченным."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_paypaid_", "").split("_")
    short_payment_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        payment_id = await find_uuid_by_prefix(session, "payments", short_payment_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not payment_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.repositories.payment_repo import PaymentRepository
        p_repo = PaymentRepository(session)
        await p_repo.mark_paid(payment_id)
        await session.commit()

    await callback.answer("✅ Платёж отмечен оплаченным!")
    # Возвращаемся к списку платежей
    await show_tutor_payments(callback, is_admin)


# ─────────────────────────────────────────────────────────────────
# УДАЛИТЬ ПЛАТЕЖ
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_delpay_"))
async def delete_payment(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Удалить платёж."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    parts = callback.data.replace("adm_delpay_", "").split("_")
    short_payment_id = parts[0]
    short_tutor_id = parts[1]

    async with get_session() as session:
        payment_id = await find_uuid_by_prefix(session, "payments", short_payment_id)
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not payment_id or not tutor_id:
            await callback.answer("Не найдено.")
            return

        from src.database.models import Payment
        payment = await session.get(Payment, payment_id)
        if payment:
            await session.delete(payment)
            await session.commit()

    await callback.answer("✅ Платёж удалён!")
    # Возвращаемся к списку платежей
    await show_tutor_payments(callback, is_admin)


# ─────────────────────────────────────────────────────────────────
# ДОХОДЫ РЕПЕТИТОРА
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_income_"))
async def show_tutor_income(callback: CallbackQuery, is_admin: bool = False) -> None:
    """Показать статистику доходов репетитора."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_income_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        # Получаем статистику
        paid_income = await session.execute(
            text("SELECT SUM(amount) FROM payments WHERE tutor_id = :tutor_id AND status = 'paid'"),
            {"tutor_id": str(tutor_id)}
        )
        total_paid = paid_income.scalar() or 0

        pending_debts = await session.execute(
            text("SELECT SUM(amount) FROM payments WHERE tutor_id = :tutor_id AND status = 'pending'"),
            {"tutor_id": str(tutor_id)}
        )
        total_pending = pending_debts.scalar() or 0

        completed_lessons = await session.execute(
            text("SELECT COUNT(*) FROM bookings WHERE tutor_id = :tutor_id AND status = 'completed'"),
            {"tutor_id": str(tutor_id)}
        )
        lessons_count = completed_lessons.scalar() or 0

        avg_check = total_paid / lessons_count if lessons_count > 0 else 0

    await callback.answer()
    await callback.message.edit_text(
        f"<b>📊 Статистика доходов</b>\n\n"
        f"💰 Получено: {total_paid}₽\n"
        f"💳 Долги: {total_pending}₽\n"
        f"📚 Проведено уроков: {lessons_count}\n"
        f"📊 Средний чек: {avg_check:.0f}₽\n\n"
        f"<i>Вы можете:</i>\n"
        f"• Редактировать платежи (изменить суммы)\n"
        f"• Добавить корректировку (увеличить/уменьшить доход)\n"
        f"• Изменить уроки (для корректировки количества)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Редактировать платежи", callback_data=f"adm_payments_{short_tutor_id}")],
                [InlineKeyboardButton(text="➕ Добавить корректировку", callback_data=f"adm_addcorr_{short_tutor_id}")],
                [InlineKeyboardButton(text="📅 Изменить уроки", callback_data=f"adm_schedule_{short_tutor_id}")],
                [InlineKeyboardButton(text="◀ К репетитору", callback_data=f"adm_tutor_{short_tutor_id}")]
            ]
        )
    )


@router.callback_query(F.data.startswith("adm_addcorr_"))
async def start_income_correction(callback: CallbackQuery, is_admin: bool = False, state: FSMContext = None) -> None:
    """Начать ввод корректировки дохода."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_addcorr_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

    await callback.answer()
    await callback.message.edit_text(
        f"<b>💰 Корректировка дохода</b>\n\n"
        f"Введите сумму корректировки:\n\n"
        f"• Положительное число — увеличит доход\n"
        f"  Пример: <code>5000</code>\n\n"
        f"• Отрицательное число — уменьшит доход\n"
        f"  Пример: <code>-2000</code>\n\n"
        f"<i>Эта сумма будет добавлена как корректировка платежей.</i>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_income_{short_tutor_id}")]
            ]
        )
    )

    if state:
        await state.set_state(AdminStates.entering_income_correction)
        await state.update_data(tutor_id=short_tutor_id)


@router.message(AdminStates.entering_income_correction)
async def process_income_correction(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка суммы корректировки дохода."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_tutor_id = data.get("tutor_id")

    try:
        correction_amount = Decimal(message.text.strip())

        # Разрешаем как положительные, так и отрицательные суммы
        if correction_amount == 0:
            await message.answer(
                "❌ Сумма корректировки не может быть нулевой.\n\n"
                "Введите положительное или отрицательное число."
            )
            return

    except (ValueError, ArithmeticError):
        await message.answer(
            "❌ Неверный формат суммы.\n\n"
            "Введите число, например: <code>5000</code> или <code>-2000</code>"
        )
        return

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await message.answer("❌ Репетитор не найден.")
            await state.clear()
            return

        # Создаем корректировочный платеж
        from src.database.models import Payment

        correction = Payment(
            id=uuid.uuid4(),
            tutor_id=tutor_id,
            user_id=None,  # Корректировка без привязки к ученику
            booking_id=None,
            amount=correction_amount,
            status="paid" if correction_amount > 0 else "paid",  # Всегда "paid" для корректировок
            payment_type="adjustment",
            created_at=datetime.now(timezone.utc),
            notes=f"Ручная корректировка (админ)"
        )

        session.add(correction)
        await session.commit()

    await state.clear()

    sign = "+" if correction_amount > 0 else ""
    await message.answer(
        f"✅ Корректировка применена!\n\n"
        f"Сумма: <b>{sign}{correction_amount}₽</b>\n\n"
        f"Изменения отразятся в статистике доходов."
    )

    # Возвращаемся к статистике доходов
    from src.bot.keyboards.admin_kb import tutor_admin_panel
    await message.answer(
        "Выберите действие:",
        reply_markup=tutor_admin_panel(short_tutor_id)
    )


# ─────────────────────────────────────────────────────────────────
# НАСТРОЙКИ ЦЕН
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_prices_"))
async def show_prices_settings(callback: CallbackQuery, is_admin: bool = False, state: FSMContext = None) -> None:
    """Показать настройки цен репетитора."""
    if not _require_admin(is_admin):
        await callback.answer("❌ Нет доступа.")
        return

    short_tutor_id = callback.data.replace("adm_prices_", "")

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await callback.answer("Репетитор не найден.")
            return

        from src.database.models import Tutor
        from sqlalchemy import select

        result = await session.execute(
            select(Tutor).where(Tutor.id == tutor_id)
        )
        tutor = result.scalar_one_or_none()

        if not tutor:
            await callback.answer("Репетитор не найден.")
            return

    await callback.answer()
    await callback.message.edit_text(
        f"<b>⚙️ Настройки цен</b>\n\n"
        f"Текущая цена урока: {tutor.default_lesson_price}₽\n\n"
        f"Отправьте новую цену числом (например: 1500)",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_tutor_{short_tutor_id}")]
            ]
        )
    )

    if state:
        await state.set_state(AdminStates.editing_tutor_price)
        await state.update_data(tutor_id=short_tutor_id)


@router.message(AdminStates.editing_tutor_price)
async def process_new_tutor_price(message: Message, state: FSMContext, is_admin: bool = False) -> None:
    """Обработка новой цены репетитора."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    data = await state.get_data()
    short_tutor_id = data.get("tutor_id")

    try:
        new_price = Decimal(message.text.strip())
        if new_price <= 0:
            await message.answer("Цена должна быть больше нуля.")
            return
    except Exception:
        await message.answer("Неверный формат. Введите число.")
        return

    async with get_session() as session:
        tutor_id = await find_uuid_by_prefix(session, "tutors", short_tutor_id)
        if not tutor_id:
            await message.answer("Репетитор не найден.")
            await state.clear()
            return

        from src.database.models import Tutor
        from sqlalchemy import select, update

        await session.execute(
            update(Tutor).where(Tutor.id == tutor_id).values(default_lesson_price=new_price)
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Цена обновлена: {new_price}₽",
        reply_markup=admin_main_menu()
    )


# ─────────────────────────────────────────────────────────────────
# СТАТИСТИКА
# ─────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Общая статистика")
async def show_global_stats(message: Message, is_admin: bool = False) -> None:
    """Показать общую статистику по всем репетиторам."""
    if not _require_admin(is_admin):
        await message.answer("❌ Нет доступа.")
        return

    async with get_session() as session:
        # Общее количество репетиторов
        tutors_count = await session.execute(text("SELECT COUNT(*) FROM tutors"))
        tutors_total = tutors_count.scalar()

        # Общее количество учеников (пользователи с назначенным репетитором)
        students_count = await session.execute(text("SELECT COUNT(*) FROM users WHERE tutor_id IS NOT NULL"))
        students_total = students_count.scalar()

        # Общее количество уроков
        bookings_count = await session.execute(text("SELECT COUNT(*) FROM bookings"))
        bookings_total = bookings_count.scalar()

        # Общий доход
        income = await session.execute(
            text("SELECT SUM(amount) FROM payments WHERE status = 'paid'")
        )
        total_income = income.scalar() or 0

        # Долги
        debts = await session.execute(
            text("SELECT SUM(amount) FROM payments WHERE status = 'pending'")
        )
        total_debts = debts.scalar() or 0

    await message.answer(
        "<b>📊 Общая статистика</b>\n\n"
        f"👥 Репетиторов: <b>{tutors_total}</b>\n"
        f"👤 Учеников: <b>{students_total}</b>\n"
        f"📅 Уроков всего: <b>{bookings_total}</b>\n\n"
        f"💚 Получено: <b>{total_income:.0f}₽</b>\n"
        f"🔴 Долги: <b>{total_debts:.0f}₽</b>\n"
        f"💛 Итого: <b>{total_income + total_debts:.0f}₽</b>"
    )
