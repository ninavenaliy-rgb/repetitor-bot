"""Referral program handlers for tutors."""

from __future__ import annotations

from typing import Optional

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config.settings import settings
from src.database.engine import get_session
from src.database.models import Tutor

router = Router(name="referral")

COMMISSION_RATE = 15  # %


@router.message(F.text == "Рефералы")
async def show_referral_page(
    message: Message, db_tutor: Optional[Tutor] = None
) -> None:
    """Страница реферальной программы."""
    if not db_tutor:
        return

    async with get_session() as session:
        from src.database.repositories.referral_repo import ReferralRepository

        ref_repo = ReferralRepository(session)
        count = await ref_repo.get_referral_count(db_tutor.id)
        total_earned = await ref_repo.get_total_commission(db_tutor.id)
        referrals = await ref_repo.get_referrals(db_tutor.id)

    ref_code = db_tutor.referral_code or "—"
    bot_username = settings.bot_username
    if bot_username:
        ref_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"
        link_text = f"\n\n🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>"
    else:
        link_text = f"\n\nВаш реферальный код: <b>{ref_code}</b>"

    referrals_text = ""
    if referrals:
        referrals_text = "\n\n<b>Ваши рефералы:</b>\n"
        for r in referrals[:10]:
            referrals_text += f"• {r.name or 'Без имени'}\n"

    balance = db_tutor.referral_balance or 0

    text = (
        f"<b>Реферальная программа</b>\n\n"
        f"Приглашайте коллег-репетиторов и зарабатывайте <b>{COMMISSION_RATE}%</b> "
        f"от каждого платежа их учеников через бот.\n"
        f"{link_text}\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"Рефералов: <b>{count}</b>\n"
        f"Заработано всего: <b>{total_earned:.0f}₽</b>\n"
        f"Баланс к выводу: <b>{balance:.0f}₽</b>"
        f"{referrals_text}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Запросить вывод", callback_data="ref_withdraw")],
        ]
    ) if balance >= 500 else None

    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "ref_withdraw")
async def request_withdrawal(callback, db_tutor: Optional[Tutor] = None) -> None:
    """Request manual withdrawal of referral balance."""
    if not db_tutor:
        return

    balance = db_tutor.referral_balance or 0
    if balance < 500:
        await callback.answer("Минимальная сумма вывода — 500₽")
        return

    # Уведомляем администратора (пока — заглушка, в продакшне отправлять на email/Telegram)
    from loguru import logger
    logger.info(
        f"Withdrawal request: tutor {db_tutor.id} ({db_tutor.name}), "
        f"balance={balance}, telegram_id={db_tutor.telegram_id}"
    )

    await callback.answer("Запрос отправлен!")
    await callback.message.edit_text(
        f"✅ Запрос на вывод <b>{balance:.0f}₽</b> принят.\n\n"
        "Мы свяжемся с вами в течение 1-2 рабочих дней для уточнения реквизитов."
    )
