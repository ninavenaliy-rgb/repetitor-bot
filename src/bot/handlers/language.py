"""Language selection handler for student interface."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.locales import t
from src.database.engine import get_session
from src.database.models import User
from src.database.repositories.user_repo import UserRepository

router = Router(name="language")

LANG_LABELS = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "de": "🇩🇪 Deutsch",
}


def language_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for selecting interface language."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="lang_de")],
        ]
    )


@router.callback_query(F.data.startswith("lang_"))
async def on_language_selected(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
) -> None:
    """Save selected language and continue to goal selection."""
    lang = callback.data.replace("lang_", "")
    if lang not in ("ru", "en", "es", "de"):
        await callback.answer()
        return

    async with get_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(db_user.telegram_id)
        if user:
            await repo.update(user, language=lang)

    await callback.answer(t(lang, "language_set"))

    # Continue to goal selection in the new language
    from src.bot.keyboards.main_menu import goal_keyboard
    from src.bot.states.registration import RegistrationStates

    await state.set_state(RegistrationStates.waiting_goal)
    await callback.message.edit_text(
        t(lang, "welcome_new"),
        reply_markup=goal_keyboard(lang),
    )
