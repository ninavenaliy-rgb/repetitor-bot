"""Клавиатуры для панели репетитора."""

from __future__ import annotations

import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_WEEKDAYS_RU = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}


def students_list_keyboard(
    students: list[dict], page: int = 0, page_size: int = 8
) -> InlineKeyboardMarkup:
    """Список учеников с пагинацией. students: [{id, name, level}]"""
    start = page * page_size
    end = start + page_size
    page_students = students[start:end]

    buttons = []
    for s in page_students:
        level = s.get("level") or "?"
        name = s.get("name") or "Без имени"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{name} ({level})",
                    callback_data=f"tp_student_{s['id']}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"tp_stpage_{page - 1}"))
    if end < len(students):
        nav.append(InlineKeyboardButton(text="Вперёд ▶", callback_data=f"tp_stpage_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def student_card_keyboard(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Действия с учеником."""
    uid = str(user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Записать на урок", callback_data=f"tp_book_{uid}"),
                InlineKeyboardButton(text="📦 Пакет уроков", callback_data=f"tp_pkg_{uid}"),
            ],
            [
                InlineKeyboardButton(text="💰 Оплаты", callback_data=f"tp_paydet_{uid}"),
                InlineKeyboardButton(text="📋 История", callback_data=f"tp_hist_{uid}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Заметка", callback_data=f"tp_note_{uid}"),
                InlineKeyboardButton(text="🎯 Цель", callback_data=f"tp_goal_{uid}"),
            ],
            [
                InlineKeyboardButton(text="✏️ Имя", callback_data=f"tp_rename_{uid}"),
            ],
            [
                InlineKeyboardButton(text="👨‍👩‍👧 Родитель", callback_data=f"tp_parent_{uid}"),
            ],
            [
                InlineKeyboardButton(text="📊 Уровень", callback_data=f"tp_setlevel_{uid}"),
                InlineKeyboardButton(text="📈 Прогресс", callback_data=f"tp_progress_{uid}"),
            ],
            [
                InlineKeyboardButton(text="💵 Цена за урок", callback_data=f"tp_setprice_{uid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К списку", callback_data="tp_students_back"),
            ],
        ]
    )


def package_size_keyboard(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Выбор размера пакета уроков."""
    uid = str(user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="4 урока", callback_data=f"tp_pkgsize_4_{uid}"),
                InlineKeyboardButton(text="8 уроков", callback_data=f"tp_pkgsize_8_{uid}"),
                InlineKeyboardButton(text="12 уроков", callback_data=f"tp_pkgsize_12_{uid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{uid}"),
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены текущего действия."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="tp_cancel_state")],
        ]
    )


def payment_method_keyboard() -> InlineKeyboardMarkup:
    """Выбор способа оплаты за пакет уроков."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 ЮKassa (карта)", callback_data="tp_pay_yookassa")],
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="tp_pay_stars")],
            [InlineKeyboardButton(text="📝 Записать вручную", callback_data="tp_pay_manual")],
        ]
    )


def lesson_summary_keyboard(booking_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Клавиатура после отметки урока как проведённого."""
    bid = str(booking_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить резюме", callback_data=f"tp_skip_summary_{bid}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена", callback_data="tp_cancel_state"
                )
            ],
        ]
    )


def schedule_keyboard(
    week_offset: int = 0,
    lesson_buttons: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    """Навигация расписания.
    lesson_buttons: list of (label, callback_data) for each lesson
    """
    rows = []
    # Per-lesson clickable buttons
    if lesson_buttons:
        for label, cb in lesson_buttons:
            rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    # Navigation
    rows.append([
        InlineKeyboardButton(text="◀ Пред.", callback_data=f"tp_week_{week_offset - 1}"),
        InlineKeyboardButton(text="Сегодня", callback_data="tp_week_0"),
        InlineKeyboardButton(text="След. ▶", callback_data=f"tp_week_{week_offset + 1}"),
    ])
    rows.append([
        InlineKeyboardButton(text="📅 Вид: месяц", callback_data=f"tp_month_{week_offset}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lesson_detail_keyboard(booking_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Действия с конкретным уроком."""
    bid = str(booking_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Проведён ✅", callback_data=f"tp_done_{bid}"),
                InlineKeyboardButton(text="Неявка ❌", callback_data=f"tp_noshow_{bid}"),
            ],
            [
                InlineKeyboardButton(text="Отменить", callback_data=f"tp_cnlbook_{bid}"),
                InlineKeyboardButton(text="Заметка", callback_data=f"tp_lnote_{bid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К расписанию", callback_data="tp_week_0"),
            ],
        ]
    )


def duration_keyboard() -> InlineKeyboardMarkup:
    """Выбор длительности урока."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="30 мин", callback_data="tp_dur_30"),
                InlineKeyboardButton(text="45 мин", callback_data="tp_dur_45"),
            ],
            [
                InlineKeyboardButton(text="60 мин", callback_data="tp_dur_60"),
                InlineKeyboardButton(text="90 мин", callback_data="tp_dur_90"),
            ],
            [
                InlineKeyboardButton(text="120 мин", callback_data="tp_dur_120"),
            ],
        ]
    )


def payments_list_keyboard(debts: list[dict]) -> InlineKeyboardMarkup:
    """Список должников. debts: [{user_id, name, count, total}]"""
    buttons = []
    for d in debts[:10]:
        name = d.get("name") or "?"
        total = d.get("total", 0)
        count = d.get("count", 0)
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{name} — {count} ур. ({total}₽)",
                    callback_data=f"tp_paydet_{d['user_id']}",
                )
            ]
        )
    if not buttons:
        buttons.append(
            [InlineKeyboardButton(text="Все оплачены ✅", callback_data="tp_noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_actions_keyboard(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Действия с оплатой ученика."""
    uid = str(user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отметить оплату", callback_data=f"tp_markpaid_{uid}"),
                InlineKeyboardButton(text="📦 Пакет уроков", callback_data=f"tp_pkg_{uid}"),
            ],
            [
                InlineKeyboardButton(text="👤 Карточка", callback_data=f"tp_student_{uid}"),
                InlineKeyboardButton(text="◀ К списку", callback_data="tp_payments_back"),
            ],
        ]
    )


def income_keyboard() -> InlineKeyboardMarkup:
    """Навигация по отчёту о доходах."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Прошлый месяц", callback_data="tp_income_prev"),
                InlineKeyboardButton(text="За всё время", callback_data="tp_income_all"),
            ],
            [
                InlineKeyboardButton(text="💼 Детальная аналитика", callback_data="tp_finance_detail"),
            ],
        ]
    )


def level_keyboard(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Выбор уровня CEFR ученика."""
    uid = str(user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="A1", callback_data=f"tp_level_A1_{uid}"),
                InlineKeyboardButton(text="A2", callback_data=f"tp_level_A2_{uid}"),
                InlineKeyboardButton(text="B1", callback_data=f"tp_level_B1_{uid}"),
            ],
            [
                InlineKeyboardButton(text="B2", callback_data=f"tp_level_B2_{uid}"),
                InlineKeyboardButton(text="C1", callback_data=f"tp_level_C1_{uid}"),
                InlineKeyboardButton(text="C2", callback_data=f"tp_level_C2_{uid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{uid}"),
            ],
        ]
    )


def progress_keyboard(user_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Выбор процента прогресса ученика."""
    uid = str(user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0%", callback_data=f"tp_setprog_0_{uid}"),
                InlineKeyboardButton(text="25%", callback_data=f"tp_setprog_25_{uid}"),
                InlineKeyboardButton(text="50%", callback_data=f"tp_setprog_50_{uid}"),
            ],
            [
                InlineKeyboardButton(text="75%", callback_data=f"tp_setprog_75_{uid}"),
                InlineKeyboardButton(text="100%", callback_data=f"tp_setprog_100_{uid}"),
            ],
            [
                InlineKeyboardButton(text="⌨️ Ввести вручную", callback_data=f"tp_prog_manual_{uid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К карточке", callback_data=f"tp_student_{uid}"),
            ],
        ]
    )
