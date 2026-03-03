"""Главное меню и общие клавиатуры."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.bot.locales import t


def tutor_reply_keyboard() -> ReplyKeyboardMarkup:
    """Постоянное меню репетитора — панель управления."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Мои ученики"),
                KeyboardButton(text="Расписание"),
            ],
            [
                KeyboardButton(text="Оплаты"),
                KeyboardButton(text="Доходы"),
            ],
            [
                KeyboardButton(text="Добавить ученика"),
                KeyboardButton(text="Заметки"),
            ],
            [
                KeyboardButton(text="📝 Составить план урока"),
                KeyboardButton(text="✅ Проверить ДЗ"),
            ],
            [
                KeyboardButton(text="Рефералы"),
                KeyboardButton(text="💎 Моя подписка"),
                KeyboardButton(text="👨‍🎓 Режим ученика"),
            ],
            [
                KeyboardButton(text="🔴 Зона риска"),
                KeyboardButton(text="💬 Отзывы"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Панель репетитора",
    )


def main_menu_reply_keyboard(lang: str = "ru", is_tutor: bool = False) -> ReplyKeyboardMarkup:
    """Постоянное меню внизу экрана — всегда видно."""
    rows = [
        [
            KeyboardButton(text=t(lang, "btn_book")),
            KeyboardButton(text=t(lang, "btn_my_lessons")),
        ],
        [
            KeyboardButton(text=t(lang, "btn_homework")),
            KeyboardButton(text=t(lang, "btn_word_of_day")),
        ],
        [
            KeyboardButton(text=t(lang, "btn_profile")),
            KeyboardButton(text="🎁 Пригласить друга"),
        ],
        [
            KeyboardButton(text="💬 Отзывы и предложения"),
        ],
    ]
    if is_tutor:
        rows.append([KeyboardButton(text="↩ Панель репетитора")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Inline-меню (используется после действий)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_book"), callback_data="booking_start"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_homework"), callback_data="homework_start"
                ),
            ],
        ]
    )


def goal_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Выбор цели при регистрации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "goal_general"), callback_data="goal_general"
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "goal_business"), callback_data="goal_business"
                ),
            ],
            [
                InlineKeyboardButton(text="IELTS / TOEFL", callback_data="goal_ielts"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "goal_oge_ege"), callback_data="goal_oge_ege"),
            ],
        ]
    )


def after_goal_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура после выбора цели."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_placement"),
                    callback_data="placement_start",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "btn_know_level"),
                    callback_data="skip_placement",
                ),
            ],
        ]
    )
