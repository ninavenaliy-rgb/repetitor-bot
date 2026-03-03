"""Subscription management service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger

from src.database.engine import get_session
from src.database.models_subscription import (
    Subscription,
    SubscriptionEventType,
    SubscriptionHistory,
    SubscriptionPlan,
    SubscriptionStatus,
    UsageTracking,
)


class SubscriptionService:
    """Business logic for subscription management."""

    async def create_trial_subscription(
        self,
        tutor_id: uuid.UUID,
        plan_code: str = "START",
        currency: str = "RUB",
    ) -> Subscription:
        """Create trial subscription for new tutor."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                SubscriptionPlanRepository,
                SubscriptionRepository,
            )

            plan_repo = SubscriptionPlanRepository(session)
            sub_repo = SubscriptionRepository(session)

            # Get plan
            plan = await plan_repo.get_by_code(plan_code)
            if not plan:
                raise ValueError(f"Plan {plan_code} not found")

            # Check if tutor already has subscription
            existing = await sub_repo.get_by_tutor(tutor_id)
            if existing:
                raise ValueError(f"Tutor {tutor_id} already has subscription")

            # Trial dates
            now = datetime.now(timezone.utc)
            trial_end = now + timedelta(days=plan.trial_days)

            # Create subscription
            subscription = await sub_repo.create(
                tutor_id=tutor_id,
                plan_id=plan.id,
                status=SubscriptionStatus.TRIAL.value,
                trial_start=now,
                trial_end=trial_end,
                current_period_start=now,
                current_period_end=trial_end,
                currency=currency,
                amount=plan.get_price(currency),
                auto_renew=True,
            )

            # Log history
            await sub_repo.add_history(
                subscription_id=subscription.id,
                tutor_id=tutor_id,
                event_type=SubscriptionEventType.TRIAL_STARTED.value,
                new_plan_id=plan.id,
                new_status=SubscriptionStatus.TRIAL.value,
                metadata={"trial_days": plan.trial_days},
            )

            # Create usage tracking for trial period
            await sub_repo.create_usage_tracking(
                subscription_id=subscription.id,
                tutor_id=tutor_id,
                period_start=now,
                period_end=trial_end,
            )

            logger.info(
                f"Trial subscription created: {subscription.id} for tutor {tutor_id}, plan {plan_code}"
            )
            return subscription

    async def activate_subscription(
        self,
        subscription_id: uuid.UUID,
        provider: str,
        provider_subscription_id: str,
    ) -> Subscription:
        """Activate subscription after successful payment."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            now = datetime.now(timezone.utc)
            next_period_end = now + timedelta(days=30)

            old_status = subscription.status

            # Update subscription
            await repo.update(
                subscription,
                status=SubscriptionStatus.ACTIVE.value,
                current_period_start=now,
                current_period_end=next_period_end,
                provider=provider,
                provider_subscription_id=provider_subscription_id,
            )

            # Log history
            await repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.ACTIVATED.value,
                old_status=old_status,
                new_status=SubscriptionStatus.ACTIVE.value,
                amount=subscription.amount,
                currency=subscription.currency,
            )

            logger.info(f"Subscription activated: {subscription.id}")
            return subscription

    async def renew_subscription(self, subscription_id: uuid.UUID) -> Subscription:
        """Renew subscription for next period."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            if not subscription.auto_renew:
                raise ValueError("Auto-renew is disabled")

            now = datetime.now(timezone.utc)
            next_period_end = now + timedelta(days=30)

            await repo.update(
                subscription,
                current_period_start=now,
                current_period_end=next_period_end,
                grace_period_end=None,  # Clear grace period if any
            )

            # Create usage tracking for new period
            await repo.create_usage_tracking(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                period_start=now,
                period_end=next_period_end,
            )

            # Log history
            await repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.RENEWED.value,
                new_status=subscription.status,
                amount=subscription.amount,
                currency=subscription.currency,
            )

            logger.info(f"Subscription renewed: {subscription.id}")
            return subscription

    async def upgrade_subscription(
        self,
        subscription_id: uuid.UUID,
        new_plan_code: str,
    ) -> Subscription:
        """Upgrade subscription to higher plan with proration."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                SubscriptionPlanRepository,
                SubscriptionRepository,
            )

            sub_repo = SubscriptionRepository(session)
            plan_repo = SubscriptionPlanRepository(session)

            subscription = await sub_repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            new_plan = await plan_repo.get_by_code(new_plan_code)
            if not new_plan:
                raise ValueError(f"Plan {new_plan_code} not found")

            old_plan = subscription.plan

            # Calculate proration
            proration = self._calculate_proration(
                subscription=subscription,
                old_plan=old_plan,
                new_plan=new_plan,
            )

            old_plan_id = subscription.plan_id

            # Update subscription
            await sub_repo.update(
                subscription,
                plan_id=new_plan.id,
                amount=new_plan.get_price(subscription.currency),
            )

            # Log history
            await sub_repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.UPGRADED.value,
                old_plan_id=old_plan_id,
                new_plan_id=new_plan.id,
                new_status=subscription.status,
                amount=proration,
                currency=subscription.currency,
                metadata={"proration_amount": str(proration)},
            )

            logger.info(
                f"Subscription upgraded: {subscription.id} from {old_plan.code} to {new_plan.code}"
            )
            return subscription

    async def downgrade_subscription(
        self,
        subscription_id: uuid.UUID,
        new_plan_code: str,
    ) -> Subscription:
        """Downgrade subscription to lower plan (effective next period)."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import (
                SubscriptionPlanRepository,
                SubscriptionRepository,
            )

            sub_repo = SubscriptionRepository(session)
            plan_repo = SubscriptionPlanRepository(session)

            subscription = await sub_repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            new_plan = await plan_repo.get_by_code(new_plan_code)
            if not new_plan:
                raise ValueError(f"Plan {new_plan_code} not found")

            old_plan_id = subscription.plan_id

            # Store downgrade in metadata, apply on next renewal
            metadata = subscription.metadata.copy()
            metadata["pending_downgrade"] = {
                "new_plan_id": str(new_plan.id),
                "new_plan_code": new_plan.code,
                "scheduled_for": subscription.current_period_end.isoformat(),
            }

            await sub_repo.update(subscription, metadata=metadata)

            # Log history
            await sub_repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.DOWNGRADED.value,
                old_plan_id=old_plan_id,
                new_plan_id=new_plan.id,
                new_status=subscription.status,
                metadata={"effective_date": subscription.current_period_end.isoformat()},
            )

            logger.info(
                f"Subscription downgrade scheduled: {subscription.id} to {new_plan.code} on {subscription.current_period_end}"
            )
            return subscription

    async def cancel_subscription(
        self,
        subscription_id: uuid.UUID,
        immediate: bool = False,
    ) -> Subscription:
        """Cancel subscription."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            now = datetime.now(timezone.utc)
            old_status = subscription.status

            if immediate:
                # Cancel immediately
                await repo.update(
                    subscription,
                    status=SubscriptionStatus.CANCELED.value,
                    auto_renew=False,
                    canceled_at=now,
                    current_period_end=now,
                )
            else:
                # Cancel at period end
                await repo.update(
                    subscription,
                    auto_renew=False,
                    canceled_at=now,
                )

            # Log history
            await repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.CANCELED.value,
                old_status=old_status,
                new_status=SubscriptionStatus.CANCELED.value if immediate else old_status,
                metadata={"immediate": immediate},
            )

            logger.info(f"Subscription canceled: {subscription.id}, immediate={immediate}")
            return subscription

    async def enter_grace_period(self, subscription_id: uuid.UUID) -> Subscription:
        """Put subscription into grace period after failed payment."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            now = datetime.now(timezone.utc)
            grace_end = now + timedelta(days=subscription.plan.grace_period_days)

            old_status = subscription.status

            await repo.update(
                subscription,
                status=SubscriptionStatus.GRACE.value,
                grace_period_end=grace_end,
            )

            # Log history
            await repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.GRACE_STARTED.value,
                old_status=old_status,
                new_status=SubscriptionStatus.GRACE.value,
                metadata={"grace_period_end": grace_end.isoformat()},
            )

            logger.warning(
                f"Subscription {subscription.id} entered grace period until {grace_end}"
            )
            return subscription

    async def expire_subscription(self, subscription_id: uuid.UUID) -> Subscription:
        """Mark subscription as expired."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_id(subscription_id)
            if not subscription:
                raise ValueError(f"Subscription {subscription_id} not found")

            old_status = subscription.status

            await repo.update(
                subscription,
                status=SubscriptionStatus.EXPIRED.value,
            )

            # Log history
            await repo.add_history(
                subscription_id=subscription.id,
                tutor_id=subscription.tutor_id,
                event_type=SubscriptionEventType.EXPIRED.value,
                old_status=old_status,
                new_status=SubscriptionStatus.EXPIRED.value,
            )

            logger.info(f"Subscription expired: {subscription.id}")
            return subscription

    async def check_and_expire_subscriptions(self) -> int:
        """Background task: check and expire subscriptions."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            now = datetime.now(timezone.utc)

            # Get subscriptions that should expire
            expired_count = 0

            # Expire grace period subscriptions
            grace_subs = await repo.get_expired_grace_subscriptions(now)
            for sub in grace_subs:
                await self.expire_subscription(sub.id)
                expired_count += 1

            # Expire trial subscriptions
            trial_subs = await repo.get_expired_trial_subscriptions(now)
            for sub in trial_subs:
                if not sub.auto_renew:
                    await self.expire_subscription(sub.id)
                    expired_count += 1

            logger.info(f"Expired {expired_count} subscriptions")
            return expired_count

    def _calculate_proration(
        self,
        subscription: Subscription,
        old_plan: SubscriptionPlan,
        new_plan: SubscriptionPlan,
    ) -> Decimal:
        """Calculate proration amount for plan upgrade."""
        now = datetime.now(timezone.utc)
        period_total = (subscription.current_period_end - subscription.current_period_start).days
        period_remaining = (subscription.current_period_end - now).days

        if period_total <= 0:
            return Decimal("0")

        # Credit for unused portion of old plan
        old_daily = old_plan.get_price(subscription.currency) / Decimal(str(period_total))
        credit = old_daily * Decimal(str(period_remaining))

        # Cost for new plan
        new_daily = new_plan.get_price(subscription.currency) / Decimal(str(period_total))
        charge = new_daily * Decimal(str(period_remaining))

        proration = charge - credit
        return max(Decimal("0"), proration)

    async def get_subscription_with_plan(
        self, tutor_id: uuid.UUID
    ) -> tuple[Subscription | None, SubscriptionPlan | None]:
        """Get subscription and plan for tutor."""
        async with get_session() as session:
            from src.database.repositories.subscription_repo import SubscriptionRepository

            repo = SubscriptionRepository(session)
            subscription = await repo.get_by_tutor(tutor_id)
            if not subscription:
                return None, None

            plan = subscription.plan
            return subscription, plan

    async def has_feature_access(self, tutor_id: uuid.UUID, feature_key: str) -> bool:
        """Check if tutor has access to feature."""
        subscription, plan = await self.get_subscription_with_plan(tutor_id)

        if not subscription or not plan:
            return False

        if not subscription.is_active:
            return False

        return plan.has_feature(feature_key)

    async def check_student_limit(self, tutor_id: uuid.UUID, current_count: int) -> bool:
        """Check if tutor is within student limit."""
        subscription, plan = await self.get_subscription_with_plan(tutor_id)

        if not subscription or not plan:
            return False

        if not subscription.is_active:
            return False

        return current_count < plan.max_students
