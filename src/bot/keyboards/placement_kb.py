"""Клавиатуры для теста уровня."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def answer_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    """Кнопки вариантов ответа."""
    buttons = []
    for idx, option in enumerate(options):
        buttons.append(
            [InlineKeyboardButton(text=option, callback_data=f"placement_ans_{idx}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def result_keyboard() -> InlineKeyboardMarkup:
    """Кнопки после результата теста."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Записаться на пробный урок", callback_data="booking_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="В главное меню", callback_data="main_menu"
                )
            ],
        ]
    )
