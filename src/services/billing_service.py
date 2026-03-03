"""Billing and payment processing service (Robokassa + Telegram Stars)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger

from config.settings import settings
from src.database.engine import get_session
from src.database.models_subscription import TransactionStatus, TransactionType
from src.services.robokassa_service import RobokassaService


class BillingService:
    """Handles payment processing via Robokassa (СБП/cards) and Telegram Stars."""

    def __init__(self) -> None:
        self._robokassa = RobokassaService()

    async def create_payment_intent(
        self,
        subscription_id: uuid.UUID,
        tutor_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a Robokassa payment intent for subscription.

        Returns:
            dict with keys: payment_url, provider_transaction_id, provider
        """
        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                BillingTransactionRepository,
            )

            billing_repo = BillingTransactionRepository(session)

            # Create pending transaction record
            transaction = await billing_repo.create(
                subscription_id=subscription_id,
                tutor_id=tutor_id,
                transaction_type=TransactionType.CHARGE.value,
                amount=float(amount),
                currency=currency,
                status=TransactionStatus.PENDING.value,
                metadata=metadata or {},
            )

            # Generate Robokassa invoice ID from transaction UUID
            inv_id = self._robokassa.generate_inv_id(transaction.id)

            # Build payment URL with СБП preference
            payment_url = self._robokassa.create_payment_url(
                amount=float(amount),
                inv_id=inv_id,
                description=description,
            )

            # Save invoice ID to metadata for webhook lookup
            await billing_repo.update_status(
                transaction,
                status=TransactionStatus.PENDING.value,
                metadata={
                    "provider": "robokassa",
                    "robokassa_inv_id": inv_id,
                },
            )

            logger.info(
                f"Robokassa payment created: InvId={inv_id} for subscription {subscription_id}"
            )

            return {
                "payment_url": payment_url,
                "provider_transaction_id": str(inv_id),
                "provider": "robokassa",
            }

    async def process_webhook(
        self,
        provider: str,
        payload: dict,
        signature: str,
    ) -> bool:
        """Process payment webhook (idempotent).

        For Robokassa: payload contains OutSum, InvId, SignatureValue.
        Returns True if processed successfully.
        """
        if provider != "robokassa":
            logger.error(f"Unknown payment provider: {provider}")
            return False

        out_sum = payload.get("OutSum", "")
        inv_id_raw = payload.get("InvId", "")

        if not out_sum or not inv_id_raw:
            logger.error("Robokassa webhook: missing OutSum or InvId")
            return False

        try:
            inv_id = int(inv_id_raw)
        except (ValueError, TypeError):
            logger.error(f"Robokassa webhook: invalid InvId={inv_id_raw}")
            return False

        # Verify signature using password2
        if not self._robokassa.verify_result_signature(out_sum, inv_id, signature):
            logger.error(f"Robokassa webhook: invalid signature for InvId={inv_id}")
            return False

        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                BillingTransactionRepository,
            )

            billing_repo = BillingTransactionRepository(session)

            # Find transaction by robokassa_inv_id in metadata
            transaction = await billing_repo.get_by_robokassa_inv_id(inv_id)
            if not transaction:
                logger.warning(f"Robokassa webhook: transaction not found for InvId={inv_id}")
                return False

            # Idempotency — skip already processed
            if transaction.status in (
                TransactionStatus.SUCCEEDED.value,
                TransactionStatus.FAILED.value,
            ):
                logger.info(f"Transaction InvId={inv_id} already processed, skipping")
                return True

            # Mark as succeeded
            await billing_repo.update_status(
                transaction,
                status=TransactionStatus.SUCCEEDED.value,
                metadata={
                    "webhook_received_at": datetime.now(timezone.utc).isoformat(),
                    "robokassa_out_sum": out_sum,
                },
            )

            logger.info(f"Robokassa payment succeeded: InvId={inv_id}")

        # Activate subscription outside the session
        from src.services.subscription_service import SubscriptionService

        sub_service = SubscriptionService()
        await sub_service.activate_subscription(
            subscription_id=transaction.subscription_id,
            provider="robokassa",
            provider_subscription_id=str(inv_id),
        )

        return True

    async def retry_failed_payment(self, subscription_id: uuid.UUID) -> Optional[str]:
        """Create a new Robokassa payment URL to retry a failed payment.

        Returns the payment URL or None if subscription not found.
        """
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            sub_repo = SubscriptionRepository(session)
            subscription = await sub_repo.get_by_id(subscription_id)

            if not subscription:
                return None

            result = await self.create_payment_intent(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                amount=Decimal(str(subscription.amount)),
                currency=subscription.currency,
                description=f"Продление подписки {subscription.plan.name}",
                metadata={"retry_attempt": True},
            )

            logger.info(
                f"Payment retry created for subscription {subscription_id}: {result['payment_url']}"
            )
            return result["payment_url"]

    async def create_refund(
        self,
        transaction_id: uuid.UUID,
        amount: Optional[Decimal] = None,
        reason: str = "requested_by_customer",
    ) -> bool:
        """Create a refund record.

        Note: Robokassa refunds are processed via Robokassa merchant panel.
        This creates an internal record only.
        """
        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                BillingTransactionRepository,
            )
            from src.database.models_subscription import BillingTransaction

            billing_repo = BillingTransactionRepository(session)
            original = await session.get(BillingTransaction, transaction_id)

            if not original or original.status != TransactionStatus.SUCCEEDED.value:
                logger.warning(f"Cannot refund transaction {transaction_id}: not found or not succeeded")
                return False

            refund_amount = amount or Decimal(str(original.amount))

            await billing_repo.create(
                subscription_id=original.subscription_id,
                tutor_id=original.tutor_id,
                transaction_type=TransactionType.REFUND.value,
                amount=float(refund_amount),
                currency=original.currency,
                status=TransactionStatus.PENDING.value,
                provider="robokassa",
                metadata={
                    "original_transaction_id": str(transaction_id),
                    "reason": reason,
                    "note": "Process refund manually in Robokassa merchant panel",
                },
            )

            logger.info(f"Refund record created for transaction {transaction_id}")
            return True
