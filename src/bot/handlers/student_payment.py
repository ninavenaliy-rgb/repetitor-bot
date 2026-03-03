"""Telegram Payments via ЮKassa — student pays for lesson package."""

from __future__ import annotations

import uuid
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery
from loguru import logger

from config.settings import settings
from src.database.engine import get_session

router = Router(name="student_payment")

COMMISSION_RATE = Decimal("0.15")  # 15% идёт реферальному счёту


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Validate payment before charging — always approve."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    """Handle successful payment — create package, notify tutor, credit referrer."""
    payment = message.successful_payment
    payload = payment.invoice_payload  # pkg_{tutor_id}_{user_id}_{size}_{price_rub}
    is_stars = payment.currency == "XTR"
    # Stars: total_amount = number of Stars (whole units)
    # RUB: total_amount = kopecks → divide by 100
    amount_rub = Decimal(payment.total_amount) if is_stars else Decimal(payment.total_amount) / 100

    try:
        parts = payload.split("_")
        # format: pkg_{tutor_id}_{user_id}_{size}_{price}
        tutor_id = uuid.UUID(parts[1])
        user_id = uuid.UUID(parts[2])
        size = int(parts[3])
    except Exception as e:
        logger.error(f"Failed to parse payment payload '{payload}': {e}")
        await message.answer(
            "Оплата прошла, но произошла ошибка при создании пакета. "
            "Свяжитесь с репетитором."
        )
        return

    async with get_session() as session:
        from src.database.repositories.package_repo import PackageRepository
        from src.database.repositories.payment_repo import PaymentRepository
        from src.database.repositories.user_repo import UserRepository
        from src.database.repositories.tutor_repo import TutorRepository
        from src.database.repositories.referral_repo import ReferralRepository

        pkg_repo = PackageRepository(session)
        pay_repo = PaymentRepository(session)
        u_repo = UserRepository(session)
        t_repo = TutorRepository(session)
        ref_repo = ReferralRepository(session)

        student = await u_repo.get_by_id(user_id)
        tutor = await t_repo.get_by_id(tutor_id)

        if not student or not tutor:
            logger.error(f"Payment: student or tutor not found: {user_id}, {tutor_id}")
            return

        # Создаём пакет
        pkg = await pkg_repo.create(
            tutor_id=tutor_id,
            user_id=user_id,
            package_type=str(size),
            total_lessons=size,
            lessons_remaining=size,
            price_total=amount_rub,
            status="active",
        )

        # Привязываем к ученику
        await u_repo.update(student, active_package_id=pkg.id)

        # Создаём запись о платеже
        await pay_repo.create(
            tutor_id=tutor_id,
            user_id=user_id,
            amount=amount_rub,
            status="paid",
            payment_type="package",
            paid_at=message.date,
        )

        # Реферальная комиссия только для рублёвых платежей
        if tutor.referred_by_id and not is_stars:
            await ref_repo.add_commission(
                referrer_id=tutor.referred_by_id,
                referred_id=tutor_id,
                payment_amount=amount_rub,
            )

        await session.commit()

    # Подтверждение студенту
    if is_stars:
        amount_str = f"{int(amount_rub)} ⭐"
    else:
        amount_str = f"{amount_rub:.0f}₽"

    await message.answer(
        f"✅ Оплата <b>{amount_str}</b> прошла успешно!\n\n"
        f"Пакет <b>{size} уроков</b> активирован.\n"
        "Уроки будут списываться автоматически по мере занятий."
    )

    # Уведомление репетитору
    if tutor and tutor.telegram_id:
        try:
            await message.bot.send_message(
                chat_id=tutor.telegram_id,
                text=(
                    f"💰 Новый платёж!\n\n"
                    f"Ученик: <b>{student.name or 'Без имени'}</b>\n"
                    f"Пакет: <b>{size} уроков</b>\n"
                    f"Сумма: <b>{amount_str}</b>\n\n"
                    "Пакет активирован, уроки будут списываться автоматически."
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to notify tutor {tutor.telegram_id}: {e}")


async def send_package_invoice(
    bot,
    student_telegram_id: int,
    tutor_id: uuid.UUID,
    user_id: uuid.UUID,
    tutor_name: str,
    size: int,
    price_rub: Decimal,
) -> None:
    """Send ЮKassa payment invoice to student for a lesson package."""
    if not settings.yookassa_provider_token:
        raise ValueError("YOOKASSA_PROVIDER_TOKEN not configured")

    price_kopecks = int(price_rub * 100)
    payload = f"pkg_{tutor_id}_{user_id}_{size}_{int(price_rub)}"

    await bot.send_invoice(
        chat_id=student_telegram_id,
        title=f"Пакет {size} уроков",
        description=f"Репетитор: {tutor_name} · {size} занятий по английскому",
        payload=payload,
        provider_token=settings.yookassa_provider_token,
        currency="RUB",
        prices=[LabeledPrice(label=f"{size} уроков", amount=price_kopecks)],
        need_name=False,
        need_phone_number=False,
        need_email=False,
    )


async def send_package_invoice_stars(
    bot,
    student_telegram_id: int,
    tutor_id: uuid.UUID,
    user_id: uuid.UUID,
    tutor_name: str,
    size: int,
    price_stars: int,
) -> None:
    """Send Telegram Stars invoice to student for a lesson package."""
    payload = f"pkg_{tutor_id}_{user_id}_{size}_{price_stars}"

    await bot.send_invoice(
        chat_id=student_telegram_id,
        title=f"Пакет {size} уроков",
        description=f"Репетитор: {tutor_name} · {size} занятий по английскому",
        payload=payload,
        provider_token="",  # пустой токен для Telegram Stars
        currency="XTR",
        prices=[LabeledPrice(label=f"{size} уроков", amount=price_stars)],
    )
