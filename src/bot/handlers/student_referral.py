"""Реферальная система для студентов."""

from __future__ import annotations

import secrets
import string

from aiogram import F, Router
from aiogram.types import Message

from src.database.engine import get_session
from src.database.models import User

router = Router(name="student_referral")

_ALPHABET = string.ascii_uppercase + string.digits  # A-Z0-9


def _gen_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


@router.message(F.text == "🎁 Пригласить друга")
async def student_referral_info(message: Message, db_user: User) -> None:
    """Показать реферальную ссылку студента."""
    if not db_user:
        return

    from config.settings import settings

    async with get_session() as session:
        from src.database.repositories.user_repo import UserRepository

        repo = UserRepository(session)
        student = await repo.get_by_id(db_user.id)

        if not student.student_referral_code:
            code = _gen_code()
            # Ensure uniqueness
            while await repo.get_by_student_referral_code(code):
                code = _gen_code()
            await repo.update(student, student_referral_code=code)
            await session.commit()
            code = student.student_referral_code = code
        else:
            code = student.student_referral_code

        invited_count = await repo.count_referrals(db_user.id)

    bot_username = settings.bot_username
    ref_link = f"https://t.me/{bot_username}?start=sref_{code}"

    bonus_line = ""
    if student.bonus_lessons > 0:
        bonus_line = f"\n🎁 Накоплено бонусов: <b>{student.bonus_lessons}</b> урок(ов)"

    await message.answer(
        f"<b>🎁 Пригласи друга</b>\n\n"
        f"Поделись ссылкой с другом:\n"
        f"<code>{ref_link}</code>\n\n"
        f"Когда друг зарегистрируется по твоей ссылке, твой репетитор получит уведомление!\n\n"
        f"👥 Ты пригласил: <b>{invited_count}</b> чел."
        f"{bonus_line}"
    )
