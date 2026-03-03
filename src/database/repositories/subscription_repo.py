"""Repositories for subscription system."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.database.models_subscription import (
    BillingTransaction,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
    SubscriptionStatus,
    UsageTracking,
)


class SubscriptionPlanRepository:
    """Repository for subscription plans."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, plan_id: uuid.UUID) -> Optional[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.code == code)
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> Sequence[SubscriptionPlan]:
        result = await self.session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.price_rub_monthly)
        )
        return result.scalars().all()


class SubscriptionRepository:
    """Repository for subscriptions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, subscription_id: uuid.UUID) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tutor(self, tutor_id: uuid.UUID) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(Subscription.tutor_id == tutor_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        tutor_id: uuid.UUID,
        plan_id: uuid.UUID,
        status: str,
        trial_start: Optional[datetime] = None,
        trial_end: Optional[datetime] = None,
        current_period_start: datetime = None,
        current_period_end: datetime = None,
        currency: str = "RUB",
        amount: float = 0,
        auto_renew: bool = True,
    ) -> Subscription:
        subscription = Subscription(
            tutor_id=tutor_id,
            plan_id=plan_id,
            status=status,
            trial_start=trial_start,
            trial_end=trial_end,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            currency=currency,
            amount=amount,
            auto_renew=auto_renew,
        )
        self.session.add(subscription)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def update(self, subscription: Subscription, **kwargs) -> Subscription:
        for key, value in kwargs.items():
            if hasattr(subscription, key):
                setattr(subscription, key, value)
        await self.session.commit()
        await self.session.refresh(subscription)
        return subscription

    async def add_history(
        self,
        subscription_id: uuid.UUID,
        tutor_id: uuid.UUID,
        event_type: str,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        old_plan_id: Optional[uuid.UUID] = None,
        new_plan_id: Optional[uuid.UUID] = None,
        amount: Optional[float] = None,
        currency: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> SubscriptionHistory:
        history = SubscriptionHistory(
            subscription_id=subscription_id,
            tutor_id=tutor_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            old_plan_id=old_plan_id,
            new_plan_id=new_plan_id,
            amount=amount,
            currency=currency,
            extra_metadata=metadata or {},
        )
        self.session.add(history)
        await self.session.commit()
        return history

    async def create_usage_tracking(
        self,
        subscription_id: uuid.UUID,
        tutor_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> UsageTracking:
        usage = UsageTracking(
            subscription_id=subscription_id,
            tutor_id=tutor_id,
            period_start=period_start,
            period_end=period_end,
        )
        self.session.add(usage)
        await self.session.commit()
        return usage

    async def get_usage_tracking(
        self, subscription_id: uuid.UUID, period_start: datetime
    ) -> Optional[UsageTracking]:
        result = await self.session.execute(
            select(UsageTracking).where(
                and_(
                    UsageTracking.subscription_id == subscription_id,
                    UsageTracking.period_start == period_start,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_usage(
        self,
        subscription_id: uuid.UUID,
        period_start: datetime,
        students_count: Optional[int] = None,
        ai_checks_used: Optional[int] = None,
    ) -> Optional[UsageTracking]:
        usage = await self.get_usage_tracking(subscription_id, period_start)
        if not usage:
            return None

        if students_count is not None:
            usage.students_count = students_count
        if ai_checks_used is not None:
            usage.ai_checks_used = ai_checks_used

        await self.session.commit()
        await self.session.refresh(usage)
        return usage

    async def get_expired_grace_subscriptions(
        self, now: datetime
    ) -> Sequence[Subscription]:
        """Get subscriptions where grace period has ended."""
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(
                and_(
                    Subscription.status == SubscriptionStatus.GRACE.value,
                    Subscription.grace_period_end <= now,
                )
            )
        )
        return result.scalars().all()

    async def get_expired_trial_subscriptions(
        self, now: datetime
    ) -> Sequence[Subscription]:
        """Get trial subscriptions that have ended."""
        result = await self.session.execute(
            select(Subscription)
            .options(joinedload(Subscription.plan))
            .where(
                and_(
                    Subscription.status == SubscriptionStatus.TRIAL.value,
                    Subscription.trial_end <= now,
                )
            )
        )
        return result.scalars().all()


class BillingTransactionRepository:
    """Repository for billing transactions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        subscription_id: uuid.UUID,
        tutor_id: uuid.UUID,
        transaction_type: str,
        amount: float,
        currency: str,
        status: str,
        provider: Optional[str] = None,
        provider_transaction_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> BillingTransaction:
        transaction = BillingTransaction(
            subscription_id=subscription_id,
            tutor_id=tutor_id,
            type=transaction_type,
            amount=amount,
            currency=currency,
            status=status,
            provider=provider or "robokassa",
            provider_transaction_id=provider_transaction_id,
            extra_metadata=metadata or {},
        )
        self.session.add(transaction)
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction

    async def get_by_provider_id(
        self, provider_transaction_id: str
    ) -> Optional[BillingTransaction]:
        """Get transaction by provider ID (for idempotency)."""
        result = await self.session.execute(
            select(BillingTransaction).where(
                BillingTransaction.provider_transaction_id == provider_transaction_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_robokassa_inv_id(
        self, inv_id: int
    ) -> Optional[BillingTransaction]:
        """Find transaction by Robokassa InvId stored in extra_metadata."""
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        result = await self.session.execute(
            select(BillingTransaction).where(
                BillingTransaction.extra_metadata["robokassa_inv_id"].astext == str(inv_id)
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        transaction: BillingTransaction,
        status: str,
        metadata: Optional[dict] = None,
    ) -> BillingTransaction:
        transaction.status = status
        if metadata:
            transaction.extra_metadata = {**transaction.extra_metadata, **metadata}
        await self.session.commit()
        await self.session.refresh(transaction)
        return transaction

    async def get_by_subscription(
        self, subscription_id: uuid.UUID, limit: int = 10
    ) -> Sequence[BillingTransaction]:
        result = await self.session.execute(
            select(BillingTransaction)
            .where(BillingTransaction.subscription_id == subscription_id)
            .order_by(BillingTransaction.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
