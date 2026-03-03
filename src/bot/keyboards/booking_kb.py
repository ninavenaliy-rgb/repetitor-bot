"""Клавиатуры для записи на урок."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_WEEKDAYS_RU = {
    0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс",
}

_MONTHS_RU = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}


def _format_day_ru(day: datetime) -> str:
    """Формат дня: 'Пн, 15 мар'."""
    wd = _WEEKDAYS_RU[day.weekday()]
    m = _MONTHS_RU[day.month]
    return f"{wd}, {day.day} {m}"


def days_keyboard(start_date: datetime, days: int = 7) -> InlineKeyboardMarkup:
    """Кнопки выбора дня на ближайшую неделю."""
    buttons = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for i in range(days):
        day = start_date + timedelta(days=i)
        label = _format_day_ru(day)

        # Добавить индикатор "Сегодня" или "Завтра"
        if day.date() == today.date():
            label = f"🔵 {label} (Сегодня)"
        elif day.date() == (today + timedelta(days=1)).date():
            label = f"{label} (Завтра)"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"booking_day_{day.strftime('%Y-%m-%d')}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="Отмена", callback_data="booking_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_keyboard(slots: list[datetime]) -> InlineKeyboardMarkup:
    """Кнопки выбора времени."""
    buttons = []
    row = []
    for slot in slots:
        # Слоты приходят уже в нужном формате, отображаем как есть
        label = slot.strftime("%H:%M")
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"booking_slot_{slot.strftime('%Y-%m-%d_%H:%M')}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Кнопка ручного ввода времени
    buttons.append(
        [
            InlineKeyboardButton(
                text="⌨️ Ввести время вручную",
                callback_data="booking_manual_time",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(text="Назад", callback_data="booking_start"),
            InlineKeyboardButton(text="Отмена", callback_data="booking_cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_keyboard(slot_str: str) -> InlineKeyboardMarkup:
    """Кнопки подтверждения записи."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить запись",
                    callback_data=f"booking_confirm_{slot_str}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Другое время", callback_data="booking_start"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="booking_cancel"),
            ],
        ]
    )
