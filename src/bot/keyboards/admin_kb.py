"""Клавиатуры для админ-панели."""

from __future__ import annotations

import uuid

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def short_id(uid: uuid.UUID | str) -> str:
    """Сокращает UUID до 12 символов для callback_data."""
    if isinstance(uid, str):
        uid = uuid.UUID(uid)
    return uid.hex[:12]


def admin_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню админ-панели."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Все репетиторы")],
            [KeyboardButton(text="📊 Общая статистика")],
            [KeyboardButton(text="🔙 Выход из админки")],
        ],
        resize_keyboard=True,
    )


def tutors_list_keyboard(tutors: list[dict], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """Список всех репетиторов с пагинацией."""
    start = page * page_size
    end = start + page_size
    page_tutors = tutors[start:end]

    buttons = []
    for t in page_tutors:
        name = t.get("name") or "Без имени"
        user_id = t.get("user_id")
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {name} (ID: {user_id})",
                callback_data=f"adm_tutor_{short_id(t['id'])}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"adm_tutors_{page - 1}"))
    if end < len(tutors):
        nav.append(InlineKeyboardButton(text="Вперёд ▶", callback_data=f"adm_tutors_{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def tutor_admin_panel(tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Панель управления репетитором."""
    tid = short_id(tutor_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Ученики", callback_data=f"adm_students_{tid}"),
                InlineKeyboardButton(text="📅 Расписание", callback_data=f"adm_schedule_{tid}"),
            ],
            [
                InlineKeyboardButton(text="💰 Оплаты", callback_data=f"adm_payments_{tid}"),
                InlineKeyboardButton(text="📊 Доходы", callback_data=f"adm_income_{tid}"),
            ],
            [
                InlineKeyboardButton(text="➕ Добавить ученика", callback_data=f"adm_addstud_{tid}"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки цен", callback_data=f"adm_prices_{tid}"),
            ],
            [
                InlineKeyboardButton(text="◀ К списку", callback_data="adm_tutors_0"),
            ],
        ]
    )


def students_admin_keyboard(students: list[dict], tutor_id: uuid.UUID, page: int = 0) -> InlineKeyboardMarkup:
    """Список учеников с админ-функциями."""
    tid = short_id(tutor_id)
    start = page * 8
    end = start + 8
    page_students = students[start:end]

    buttons = []
    for s in page_students:
        name = s.get("name") or "Без имени"
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {name}",
                callback_data=f"adm_edit_student_{short_id(s['id'])}_{tid}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"adm_stupage_{tid}_{page - 1}"))
    if end < len(students):
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"adm_stupage_{tid}_{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(text="◀ К репетитору", callback_data=f"adm_tutor_{tid}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def student_edit_keyboard(student_id: uuid.UUID, tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Редактирование данных ученика."""
    sid = short_id(student_id)
    tid = short_id(tutor_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 Цена урока", callback_data=f"adm_edprice_{sid}_{tid}"),
                InlineKeyboardButton(text="📝 Заметка", callback_data=f"adm_ednote_{sid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="📊 Уровень", callback_data=f"adm_edlevel_{sid}_{tid}"),
                InlineKeyboardButton(text="📈 Прогресс", callback_data=f"adm_edprog_{sid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_delstud_{sid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="◀ Назад", callback_data=f"adm_students_{tid}"),
            ],
        ]
    )


def payments_admin_keyboard(payments: list[dict], tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Список оплат с возможностью редактирования."""
    tid = short_id(tutor_id)
    buttons = []

    for p in payments[:10]:
        status = "✅" if p.get("status") == "paid" else "❌"
        amount = p.get("amount", 0)
        user_name = p.get("user_name") or "?"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {user_name} - {amount}₽",
                callback_data=f"adm_editpay_{short_id(p['id'])}_{tid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Добавить платёж", callback_data=f"adm_addpay_{tid}")
    ])
    buttons.append([
        InlineKeyboardButton(text="◀ К репетитору", callback_data=f"adm_tutor_{tid}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_edit_keyboard(payment_id: uuid.UUID, tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Редактирование платежа."""
    pid = short_id(payment_id)
    tid = short_id(tutor_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отметить оплаченным", callback_data=f"adm_paypaid_{pid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="💰 Изменить сумму", callback_data=f"adm_payamt_{pid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_delpay_{pid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="◀ Назад", callback_data=f"adm_payments_{tid}"),
            ],
        ]
    )


def schedule_admin_keyboard(bookings: list[dict], tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Расписание с возможностью редактирования."""
    from datetime import timedelta
    MOSCOW_OFFSET = timedelta(hours=3)

    tid = short_id(tutor_id)
    buttons = []

    for b in bookings[:10]:
        dt = b.get("scheduled_at")
        user_name = b.get("user_name") or "?"
        status_icons = {"planned": "📅", "completed": "✅", "cancelled": "❌", "no_show": "🚫"}
        status = status_icons.get(b.get("status"), "?")

        if dt:
            # Конвертируем UTC → Moscow для отображения
            dt_moscow = dt + MOSCOW_OFFSET
            label = f"{status} {dt_moscow.strftime('%d.%m %H:%M')} - {user_name}"
        else:
            label = f"{status} {user_name}"

        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"adm_editbook_{short_id(b['id'])}_{tid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="◀ К репетитору", callback_data=f"adm_tutor_{tid}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def booking_edit_keyboard(booking_id: uuid.UUID, tutor_id: uuid.UUID) -> InlineKeyboardMarkup:
    """Редактирование урока."""
    bid = short_id(booking_id)
    tid = short_id(tutor_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"adm_booktime_{bid}_{tid}"),
                InlineKeyboardButton(text="⏱ Длительность", callback_data=f"adm_bookdur_{bid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="✅ Проведён", callback_data=f"adm_bookdone_{bid}_{tid}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"adm_bookcancel_{bid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_delbook_{bid}_{tid}"),
            ],
            [
                InlineKeyboardButton(text="◀ Назад", callback_data=f"adm_schedule_{tid}"),
            ],
        ]
    )


def cancel_admin_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены для админ-панели."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_cancel")],
        ]
    )
