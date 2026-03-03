"""Billing через Telegram Stars (встроенная валюта Telegram)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment
from loguru import logger
from sqlalchemy import select

from src.database.engine import get_session
from src.database.models_subscription import BillingTransaction, TransactionStatus, TransactionType


class TelegramStarsBilling:
    """Billing через Telegram Stars (1 Star ≈ 20₽)."""

    # Stars цены согласованы с рублёвыми тарифами (1 Star ≈ 20₽)
    PRICES_IN_STARS = {
        "START": 50,   # 990₽ → 50 Stars
        "PRO": 100,    # 1990₽ → 100 Stars
    }

    async def create_invoice(
        self,
        bot: Bot,
        chat_id: int,
        subscription_id: uuid.UUID,
        tutor_id: uuid.UUID,
        plan_code: str,
        plan_name: str,
        description: str,
    ) -> dict:
        """Создать invoice и отправить пользователю.

        Returns:
            dict: {"status": "sent", "transaction_id": str, "price_stars": int}
        """
        price_stars = self.PRICES_IN_STARS.get(plan_code, 50)

        async with get_session() as session:
            from src.database.repositories.subscription_repo import BillingTransactionRepository

            billing_repo = BillingTransactionRepository(session)

            transaction = await billing_repo.create(
                subscription_id=subscription_id,
                tutor_id=tutor_id,
                transaction_type=TransactionType.CHARGE.value,
                amount=float(price_stars),
                currency="XTR",
                status=TransactionStatus.PENDING.value,
                provider="telegram_stars",
                metadata={"plan_code": plan_code, "plan_name": plan_name},
            )

            try:
                await bot.send_invoice(
                    chat_id=chat_id,
                    title=f"Подписка {plan_name}",
                    description=description,
                    payload=f"subscription_{subscription_id}_{transaction.id}",
                    provider_token="",  # Пустой = Telegram Stars
                    currency="XTR",
                    prices=[LabeledPrice(label=f"Подписка {plan_name}", amount=price_stars)],
                    start_parameter=f"sub_{subscription_id}",
                )

                logger.info(
                    f"Stars invoice sent: {transaction.id} — {price_stars} Stars для {plan_name}"
                )
                return {
                    "status": "sent",
                    "transaction_id": str(transaction.id),
                    "price_stars": price_stars,
                }

            except Exception as e:
                logger.error(f"Ошибка отправки Stars invoice: {e}")
                await billing_repo.update_status(
                    transaction,
                    status=TransactionStatus.FAILED.value,
                    metadata={"error": str(e)},
                )
                raise

    async def handle_pre_checkout(self, pre_checkout_query: PreCheckoutQuery) -> bool:
        """Проверить платёж перед списанием Stars."""
        try:
            payload = pre_checkout_query.invoice_payload
            parts = payload.split("_")

            if len(parts) != 3 or parts[0] != "subscription":
                logger.error(f"Некорректный payload: {payload}")
                await pre_checkout_query.answer(ok=False, error_message="Некорректный формат платежа")
                return False

            transaction_id = uuid.UUID(parts[2])

            async with get_session() as session:
                result = await session.execute(
                    select(BillingTransaction).where(BillingTransaction.id == transaction_id)
                )
                transaction = result.scalar_one_or_none()

                if not transaction:
                    logger.error(f"Транзакция {transaction_id} не найдена")
                    await pre_checkout_query.answer(ok=False, error_message="Транзакция не найдена")
                    return False

                if transaction.status != TransactionStatus.PENDING.value:
                    logger.warning(f"Транзакция {transaction_id} уже обработана: {transaction.status}")
                    await pre_checkout_query.answer(ok=False, error_message="Транзакция уже обработана")
                    return False

            await pre_checkout_query.answer(ok=True)
            logger.info(f"Pre-checkout одобрен: {transaction_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка pre-checkout: {e}")
            await pre_checkout_query.answer(ok=False, error_message="Ошибка при проверке платежа")
            return False

    async def handle_successful_payment(
        self, payment: SuccessfulPayment, user_id: int
    ) -> bool:
        """Обработать успешную оплату Stars и активировать подписку."""
        try:
            payload = payment.invoice_payload
            parts = payload.split("_")

            if len(parts) != 3 or parts[0] != "subscription":
                logger.error(f"Некорректный payload при успешной оплате: {payload}")
                return False

            subscription_id = uuid.UUID(parts[1])
            transaction_id = uuid.UUID(parts[2])
            provider_charge_id = payment.provider_payment_charge_id

            async with get_session() as session:
                from src.database.repositories.subscription_repo import BillingTransactionRepository

                billing_repo = BillingTransactionRepository(session)

                # Idempotency — проверить дублирование
                existing = await billing_repo.get_by_provider_id(provider_charge_id)
                if existing and existing.status == TransactionStatus.SUCCEEDED.value:
                    logger.info(f"Платёж {provider_charge_id} уже обработан (idempotency)")
                    return True

                result = await session.execute(
                    select(BillingTransaction).where(BillingTransaction.id == transaction_id)
                )
                transaction = result.scalar_one_or_none()

                if not transaction:
                    logger.error(f"Транзакция {transaction_id} не найдена")
                    return False

                await billing_repo.update_status(
                    transaction,
                    status=TransactionStatus.SUCCEEDED.value,
                    metadata={
                        "provider_payment_charge_id": provider_charge_id,
                        "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                        "paid_at": datetime.now(timezone.utc).isoformat(),
                        "total_amount": payment.total_amount,
                    },
                )

                transaction.provider_transaction_id = provider_charge_id
                await session.commit()

            # Активировать подписку
            from src.services.subscription_service import SubscriptionService

            sub_service = SubscriptionService()
            await sub_service.activate_subscription(
                subscription_id=subscription_id,
                provider="telegram_stars",
                provider_subscription_id=provider_charge_id,
            )

            logger.info(f"Stars оплата успешна: {provider_charge_id}, подписка {subscription_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обработки Stars платежа: {e}")
            return False
