"""Запись на урок — выбор дня, времени, подтверждение."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.bot.keyboards.booking_kb import (
    _format_day_ru,
    confirm_booking_keyboard,
    days_keyboard,
    slots_keyboard,
)
from src.bot.keyboards.main_menu import main_menu_keyboard
from src.bot.states.booking_states import BookingStates
from src.database.models import User
from src.services.booking_service import BookingService
from src.utils.exceptions import SlotConflictError

router = Router(name="booking")
_booking_service = BookingService()

DEMO_CALENDAR_ID = "primary"

# Московское время (UTC+3)
MOSCOW_OFFSET = timedelta(hours=3)


async def start_booking_from_message(message: Message, state: FSMContext) -> None:
    """Начать запись из reply-клавиатуры (вызывается из start.py)."""
    await state.set_state(BookingStates.selecting_day)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    await message.answer(
        "Выберите день для урока:",
        reply_markup=days_keyboard(today),
    )


@router.callback_query(F.data == "booking_start")
async def start_booking(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать выбор дня."""
    await state.set_state(BookingStates.selecting_day)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    await callback.answer()
    await callback.message.edit_text(
        "Выберите день для урока:",
        reply_markup=days_keyboard(today),
    )


@router.callback_query(
    BookingStates.selecting_day, F.data.startswith("booking_day_")
)
async def on_day_selected(
    callback: CallbackQuery, state: FSMContext, db_user: User
) -> None:
    """Показать доступные слоты на выбранный день."""
    date_str = callback.data.replace("booking_day_", "")
    selected_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Когда репетитор записывает студента — tutor_id берём из FSM state
    fsm_data = await state.get_data()
    tutor_id = fsm_data.get("booking_tutor_id") or db_user.tutor_id
    if not tutor_id:
        await callback.answer("Репетитор ещё не назначен. Обратитесь к преподавателю.")
        return

    slots = await _booking_service.get_available_slots(
        tutor_id=tutor_id,
        calendar_id=DEMO_CALENDAR_ID,
        date=selected_date,
    )

    if not slots:
        await callback.answer("В этот день нет свободных слотов.")
        return

    await state.set_state(BookingStates.selecting_slot)
    await state.update_data(selected_date=date_str)

    day_label = _format_day_ru(selected_date)
    await callback.answer()
    await callback.message.edit_text(
        f"Свободное время на <b>{day_label}</b>:",
        reply_markup=slots_keyboard(slots),
    )


@router.callback_query(
    BookingStates.selecting_slot, F.data.startswith("booking_slot_")
)
async def on_slot_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Подтверждение записи."""
    slot_str = callback.data.replace("booking_slot_", "")
    # Слот приходит в московском времени (naive), конвертируем в UTC
    slot_dt_moscow_naive = datetime.strptime(slot_str, "%Y-%m-%d_%H:%M")
    # Конвертируем MSK → UTC: вычитаем 3 часа и добавляем timezone
    slot_dt_utc = (slot_dt_moscow_naive - MOSCOW_OFFSET).replace(tzinfo=timezone.utc)

    await state.set_state(BookingStates.confirming)
    await state.update_data(selected_slot=slot_str)

    fsm_data2 = await state.get_data()
    duration_preview = int(fsm_data2.get("selected_duration", 60))

    day_label = _format_day_ru(slot_dt_utc)
    # Для отображения используем исходное московское время
    slot_moscow_display = slot_dt_moscow_naive
    await callback.answer()
    await callback.message.edit_text(
        f"Подтвердите запись:\n\n"
        f"<b>{day_label} в {slot_moscow_display.strftime('%H:%M')}</b>\n"
        f"Длительность: {duration_preview} минут\n\n"
        f"Всё верно?",
        reply_markup=confirm_booking_keyboard(slot_str),
    )


@router.callback_query(
    BookingStates.confirming, F.data.startswith("booking_confirm_")
)
async def on_booking_confirmed(
    callback: CallbackQuery, state: FSMContext, db_user: User
) -> None:
    """Финализация записи."""
    slot_str = callback.data.replace("booking_confirm_", "")
    # Слот приходит в московском времени (naive), конвертируем в UTC
    slot_dt_moscow_naive = datetime.strptime(slot_str, "%Y-%m-%d_%H:%M")
    # Конвертируем MSK → UTC: вычитаем 3 часа и добавляем timezone
    slot_dt_utc = (slot_dt_moscow_naive - MOSCOW_OFFSET).replace(tzinfo=timezone.utc)

    fsm_data = await state.get_data()
    tutor_id_raw = fsm_data.get("booking_tutor_id") or db_user.tutor_id
    if not tutor_id_raw:
        await callback.answer("Репетитор не назначен.")
        await state.clear()
        return
    tutor_id = uuid.UUID(str(tutor_id_raw))

    # Если репетитор записывает студента — user_id берём из FSM state
    booking_for = fsm_data.get("booking_for_user")
    student_id = uuid.UUID(booking_for) if booking_for else db_user.id
    duration = int(fsm_data.get("selected_duration", 60))

    try:
        await _booking_service.create_booking(
            tutor_id=uuid.UUID(str(tutor_id)),
            user_id=student_id,
            calendar_id=DEMO_CALENDAR_ID,
            scheduled_at=slot_dt_utc,
            duration_min=duration,
        )

        day_label = _format_day_ru(slot_dt_utc)
        # Для отображения используем исходное московское время
        await state.clear()
        await callback.answer("Записано!")
        await callback.message.edit_text(
            f"Вы записаны на урок!\n\n"
            f"<b>{day_label} в {slot_dt_moscow_naive.strftime('%H:%M')}</b>\n"
            f"Длительность: {duration} минут\n\n"
            f"Я напомню вам перед занятием.",
            reply_markup=main_menu_keyboard(),
        )

    except SlotConflictError:
        await callback.answer("Это время уже занято. Выберите другое.")
        await state.set_state(BookingStates.selecting_day)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        await callback.message.edit_text(
            "К сожалению, это время уже занято.\nВыберите другой день:",
            reply_markup=days_keyboard(today),
        )


@router.callback_query(
    BookingStates.selecting_slot, F.data == "booking_manual_time"
)
async def on_manual_time_request(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Переход к ручному вводу времени."""
    await state.set_state(BookingStates.entering_manual_time)
    await callback.answer()
    await callback.message.edit_text(
        "Введите время в формате <b>ЧЧ:ММ</b>\n\n"
        "Например: 14:30 или 09:00",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀ Назад к слотам", callback_data="booking_back_to_slots"
                    )
                ],
                [
                    InlineKeyboardButton(text="Отмена", callback_data="booking_cancel")
                ],
            ]
        ),
    )


@router.callback_query(
    BookingStates.entering_manual_time, F.data == "booking_back_to_slots"
)
async def back_to_slots(
    callback: CallbackQuery, state: FSMContext, db_user: User
) -> None:
    """Вернуться к выбору слотов из календаря."""
    fsm_data = await state.get_data()
    date_str = fsm_data.get("selected_date")

    if not date_str:
        await callback.answer("Ошибка: дата не найдена.")
        await state.clear()
        return

    selected_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    tutor_id = fsm_data.get("booking_tutor_id") or db_user.tutor_id

    if not tutor_id:
        await callback.answer("Репетитор не назначен.")
        await state.clear()
        return

    slots = await _booking_service.get_available_slots(
        tutor_id=tutor_id,
        calendar_id=DEMO_CALENDAR_ID,
        date=selected_date,
    )

    await state.set_state(BookingStates.selecting_slot)
    day_label = _format_day_ru(selected_date)
    await callback.answer()
    await callback.message.edit_text(
        f"Свободное время на <b>{day_label}</b>:",
        reply_markup=slots_keyboard(slots),
    )


@router.message(BookingStates.entering_manual_time)
async def on_manual_time_entered(
    message: Message, state: FSMContext, db_user: User
) -> None:
    """Обработка ручного ввода времени."""
    time_text = message.text.strip()

    # Валидация формата HH:MM
    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    match = re.match(time_pattern, time_text)

    if not match:
        await message.answer(
            "❌ Неверный формат времени.\n\n"
            "Введите время в формате <b>ЧЧ:ММ</b>, например: 14:30 или 09:00"
        )
        return

    # Получение выбранной даты
    fsm_data = await state.get_data()
    date_str = fsm_data.get("selected_date")

    if not date_str:
        await message.answer("❌ Ошибка: дата не найдена. Начните заново.")
        await state.clear()
        return

    # Парсинг даты и времени
    selected_date = datetime.strptime(date_str, "%Y-%m-%d")
    hours, minutes = int(match.group(1)), int(match.group(2))
    # Пользователь вводит московское время, конвертируем в UTC
    # Создаем naive datetime с московским временем
    slot_dt_moscow_naive = datetime(selected_date.year, selected_date.month, selected_date.day, hours, minutes, 0, 0)
    # Конвертируем Moscow → UTC: вычитаем 3 часа и добавляем timezone
    slot_dt_utc = (slot_dt_moscow_naive - MOSCOW_OFFSET).replace(tzinfo=timezone.utc)

    # Проверка: время не в прошлом (минимум через 1 час)
    now = datetime.now(timezone.utc)
    if slot_dt_utc <= now + timedelta(hours=1):
        # Проверяем: может быть выбрана вчерашняя дата?
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if selected_date.date() < today.date():
            await message.answer(
                "❌ Выбранная дата уже прошла!\n\n"
                "Вернитесь назад и выберите сегодняшний день или будущую дату."
            )
        else:
            # Показываем текущее московское время
            now_moscow = now + MOSCOW_OFFSET
            await message.answer(
                "❌ Время уже прошло или слишком близко.\n\n"
                f"Сейчас: {now_moscow.strftime('%H:%M')} (МСК)\n"
                f"Выберите время как минимум через 1 час от текущего момента."
            )
        return

    # Переход к подтверждению
    # slot_str сохраняем в московском времени (как ввёл пользователь)
    slot_str = slot_dt_moscow_naive.strftime("%Y-%m-%d_%H:%M")
    await state.set_state(BookingStates.confirming)
    await state.update_data(selected_slot=slot_str)

    duration_preview = int(fsm_data.get("selected_duration", 60))
    day_label = _format_day_ru(slot_dt_utc)
    # Для отображения используем исходное московское время
    slot_moscow_display = slot_dt_moscow_naive

    await message.answer(
        f"Подтвердите запись:\n\n"
        f"<b>{day_label} в {slot_moscow_display.strftime('%H:%M')}</b>\n"
        f"Длительность: {duration_preview} минут\n\n"
        f"Всё верно?",
        reply_markup=confirm_booking_keyboard(slot_str),
    )


@router.callback_query(F.data == "booking_cancel")
async def on_booking_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена записи."""
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Запись отменена. Выберите действие:",
        reply_markup=main_menu_keyboard(),
    )
