"""Product metrics for SaaS: MRR, LTV, CAC, churn."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import and_, func, select

from src.database.engine import get_session
from src.database.models_subscription import (
    BillingTransaction,
    Subscription,
    SubscriptionHistory,
    SubscriptionStatus,
    TransactionStatus,
    TransactionType,
)


@dataclass
class MRRMetrics:
    """Monthly Recurring Revenue metrics."""

    current_mrr: Decimal  # Current MRR
    new_mrr: Decimal  # MRR from new subscriptions this month
    expansion_mrr: Decimal  # MRR from upgrades
    contraction_mrr: Decimal  # MRR lost from downgrades
    churn_mrr: Decimal  # MRR lost from cancellations
    net_new_mrr: Decimal  # new + expansion - contraction - churn
    mrr_growth_rate: float  # Percentage growth


@dataclass
class CustomerMetrics:
    """Customer lifecycle metrics."""

    total_customers: int
    active_customers: int
    trial_customers: int
    churned_this_month: int
    new_this_month: int
    churn_rate: float  # Percentage
    ltv: Decimal  # Lifetime Value
    cac: Decimal  # Customer Acquisition Cost
    ltv_cac_ratio: float  # LTV / CAC


@dataclass
class RevenueMetrics:
    """Revenue and transaction metrics."""

    total_revenue: Decimal  # All-time
    revenue_this_month: Decimal
    revenue_last_month: Decimal
    average_revenue_per_user: Decimal  # ARPU
    successful_transactions: int
    failed_transactions: int
    refunds_count: int
    refunds_amount: Decimal


class ProductMetricsService:
    """Calculate SaaS product metrics."""

    async def get_mrr_metrics(
        self, month: Optional[datetime] = None
    ) -> MRRMetrics:
        """Calculate MRR metrics for a given month."""
        if month is None:
            month = datetime.now(timezone.utc)

        month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month.month == 12:
            month_end = month.replace(year=month.year + 1, month=1, day=1)
        else:
            month_end = month.replace(month=month.month + 1, day=1)

        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

        async with get_session() as session:
            # Current MRR (all active subscriptions)
            result = await session.execute(
                select(func.sum(Subscription.amount)).where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.ACTIVE.value,
                            SubscriptionStatus.GRACE.value,
                        ]
                    )
                )
            )
            current_mrr = result.scalar_one() or Decimal("0")

            # New MRR (subscriptions created this month)
            result = await session.execute(
                select(func.sum(Subscription.amount)).where(
                    and_(
                        Subscription.created_at >= month_start,
                        Subscription.created_at < month_end,
                        Subscription.status != SubscriptionStatus.CANCELED.value,
                    )
                )
            )
            new_mrr = result.scalar_one() or Decimal("0")

            # Expansion MRR (upgrades this month)
            result = await session.execute(
                select(func.sum(SubscriptionHistory.amount)).where(
                    and_(
                        SubscriptionHistory.event_type == "upgraded",
                        SubscriptionHistory.created_at >= month_start,
                        SubscriptionHistory.created_at < month_end,
                    )
                )
            )
            expansion_mrr = result.scalar_one() or Decimal("0")

            # Contraction MRR (downgrades this month)
            result = await session.execute(
                select(func.sum(SubscriptionHistory.amount)).where(
                    and_(
                        SubscriptionHistory.event_type == "downgraded",
                        SubscriptionHistory.created_at >= month_start,
                        SubscriptionHistory.created_at < month_end,
                    )
                )
            )
            contraction_mrr = result.scalar_one() or Decimal("0")

            # Churn MRR (cancellations this month)
            result = await session.execute(
                select(func.sum(Subscription.amount)).where(
                    and_(
                        Subscription.status == SubscriptionStatus.CANCELED.value,
                        Subscription.canceled_at >= month_start,
                        Subscription.canceled_at < month_end,
                    )
                )
            )
            churn_mrr = result.scalar_one() or Decimal("0")

            # Previous month MRR for growth rate
            result = await session.execute(
                select(func.sum(Subscription.amount)).where(
                    and_(
                        Subscription.created_at < month_start,
                        Subscription.status.in_(
                            [
                                SubscriptionStatus.ACTIVE.value,
                                SubscriptionStatus.GRACE.value,
                            ]
                        ),
                    )
                )
            )
            prev_mrr = result.scalar_one() or Decimal("0")

        # Calculate net new MRR
        net_new_mrr = new_mrr + expansion_mrr - contraction_mrr - churn_mrr

        # Calculate growth rate
        if prev_mrr > 0:
            mrr_growth_rate = float((current_mrr - prev_mrr) / prev_mrr * 100)
        else:
            mrr_growth_rate = 0.0

        return MRRMetrics(
            current_mrr=current_mrr,
            new_mrr=new_mrr,
            expansion_mrr=expansion_mrr,
            contraction_mrr=contraction_mrr,
            churn_mrr=churn_mrr,
            net_new_mrr=net_new_mrr,
            mrr_growth_rate=mrr_growth_rate,
        )

    async def get_customer_metrics(
        self, month: Optional[datetime] = None
    ) -> CustomerMetrics:
        """Calculate customer lifecycle metrics."""
        if month is None:
            month = datetime.now(timezone.utc)

        month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month.month == 12:
            month_end = month.replace(year=month.year + 1, month=1, day=1)
        else:
            month_end = month.replace(month=month.month + 1, day=1)

        async with get_session() as session:
            # Total customers (all time)
            result = await session.execute(select(func.count(Subscription.id)))
            total_customers = result.scalar_one()

            # Active customers
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.TRIAL.value,
                            SubscriptionStatus.ACTIVE.value,
                            SubscriptionStatus.GRACE.value,
                        ]
                    )
                )
            )
            active_customers = result.scalar_one()

            # Trial customers
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.status == SubscriptionStatus.TRIAL.value
                )
            )
            trial_customers = result.scalar_one()

            # New customers this month
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    and_(
                        Subscription.created_at >= month_start,
                        Subscription.created_at < month_end,
                    )
                )
            )
            new_this_month = result.scalar_one()

            # Churned this month
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    and_(
                        Subscription.status.in_(
                            [
                                SubscriptionStatus.CANCELED.value,
                                SubscriptionStatus.EXPIRED.value,
                            ]
                        ),
                        Subscription.canceled_at >= month_start,
                        Subscription.canceled_at < month_end,
                    )
                )
            )
            churned_this_month = result.scalar_one()

            # Calculate churn rate
            customers_start_of_month = active_customers + churned_this_month
            if customers_start_of_month > 0:
                churn_rate = (churned_this_month / customers_start_of_month) * 100
            else:
                churn_rate = 0.0

        # Calculate LTV and CAC
        ltv = await self._calculate_ltv()
        cac = await self._calculate_cac(month)

        # LTV/CAC ratio
        if cac > 0:
            ltv_cac_ratio = float(ltv / cac)
        else:
            ltv_cac_ratio = 0.0

        return CustomerMetrics(
            total_customers=total_customers,
            active_customers=active_customers,
            trial_customers=trial_customers,
            churned_this_month=churned_this_month,
            new_this_month=new_this_month,
            churn_rate=churn_rate,
            ltv=ltv,
            cac=cac,
            ltv_cac_ratio=ltv_cac_ratio,
        )

    async def _calculate_ltv(self) -> Decimal:
        """Calculate average customer lifetime value.

        LTV = ARPU × Customer Lifetime
        Customer Lifetime = 1 / Churn Rate
        """
        async with get_session() as session:
            # Average revenue per user
            result = await session.execute(
                select(func.avg(Subscription.amount)).where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.ACTIVE.value,
                            SubscriptionStatus.GRACE.value,
                        ]
                    )
                )
            )
            arpu = result.scalar_one() or Decimal("0")

            # Calculate churn rate for last 3 months
            three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    and_(
                        Subscription.status.in_(
                            [
                                SubscriptionStatus.CANCELED.value,
                                SubscriptionStatus.EXPIRED.value,
                            ]
                        ),
                        Subscription.canceled_at >= three_months_ago,
                    )
                )
            )
            churned = result.scalar_one()

            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.created_at >= three_months_ago
                )
            )
            total = result.scalar_one()

            if total > 0:
                monthly_churn_rate = (churned / total) / 3  # Average per month
            else:
                monthly_churn_rate = 0.05  # Default 5%

            if monthly_churn_rate > 0:
                customer_lifetime_months = 1 / monthly_churn_rate
            else:
                customer_lifetime_months = 20  # Default 20 months

            ltv = arpu * Decimal(str(customer_lifetime_months))
            return ltv

    async def _calculate_cac(self, month: datetime) -> Decimal:
        """Calculate customer acquisition cost.

        CAC = Marketing Spend / New Customers

        For now, using a fixed estimate per customer.
        In production, would track marketing expenses.
        """
        # Simplified: assume 500₽ CAC per customer
        # In reality, track actual marketing spend
        return Decimal("500")

    async def get_revenue_metrics(
        self, month: Optional[datetime] = None
    ) -> RevenueMetrics:
        """Calculate revenue metrics."""
        if month is None:
            month = datetime.now(timezone.utc)

        month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month.month == 12:
            month_end = month.replace(year=month.year + 1, month=1, day=1)
        else:
            month_end = month.replace(month=month.month + 1, day=1)

        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

        async with get_session() as session:
            # Total revenue (all time)
            result = await session.execute(
                select(func.sum(BillingTransaction.amount)).where(
                    and_(
                        BillingTransaction.transaction_type == TransactionType.CHARGE.value,
                        BillingTransaction.status == TransactionStatus.SUCCEEDED.value,
                    )
                )
            )
            total_revenue = result.scalar_one() or Decimal("0")

            # Revenue this month
            result = await session.execute(
                select(func.sum(BillingTransaction.amount)).where(
                    and_(
                        BillingTransaction.transaction_type == TransactionType.CHARGE.value,
                        BillingTransaction.status == TransactionStatus.SUCCEEDED.value,
                        BillingTransaction.created_at >= month_start,
                        BillingTransaction.created_at < month_end,
                    )
                )
            )
            revenue_this_month = result.scalar_one() or Decimal("0")

            # Revenue last month
            result = await session.execute(
                select(func.sum(BillingTransaction.amount)).where(
                    and_(
                        BillingTransaction.transaction_type == TransactionType.CHARGE.value,
                        BillingTransaction.status == TransactionStatus.SUCCEEDED.value,
                        BillingTransaction.created_at >= prev_month_start,
                        BillingTransaction.created_at < month_start,
                    )
                )
            )
            revenue_last_month = result.scalar_one() or Decimal("0")

            # Active customers for ARPU
            result = await session.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.ACTIVE.value,
                            SubscriptionStatus.GRACE.value,
                        ]
                    )
                )
            )
            active_customers = result.scalar_one()

            # ARPU
            if active_customers > 0:
                average_revenue_per_user = total_revenue / Decimal(str(active_customers))
            else:
                average_revenue_per_user = Decimal("0")

            # Successful transactions
            result = await session.execute(
                select(func.count(BillingTransaction.id)).where(
                    BillingTransaction.status == TransactionStatus.SUCCEEDED.value
                )
            )
            successful_transactions = result.scalar_one()

            # Failed transactions
            result = await session.execute(
                select(func.count(BillingTransaction.id)).where(
                    BillingTransaction.status == TransactionStatus.FAILED.value
                )
            )
            failed_transactions = result.scalar_one()

            # Refunds
            result = await session.execute(
                select(
                    func.count(BillingTransaction.id),
                    func.sum(BillingTransaction.amount),
                ).where(BillingTransaction.transaction_type == TransactionType.REFUND.value)
            )
            row = result.one()
            refunds_count = row[0] or 0
            refunds_amount = row[1] or Decimal("0")

        return RevenueMetrics(
            total_revenue=total_revenue,
            revenue_this_month=revenue_this_month,
            revenue_last_month=revenue_last_month,
            average_revenue_per_user=average_revenue_per_user,
            successful_transactions=successful_transactions,
            failed_transactions=failed_transactions,
            refunds_count=refunds_count,
            refunds_amount=refunds_amount,
        )

    async def get_dashboard_summary(self) -> dict:
        """Get complete metrics dashboard."""
        mrr = await self.get_mrr_metrics()
        customers = await self.get_customer_metrics()
        revenue = await self.get_revenue_metrics()

        return {
            "mrr": {
                "current": float(mrr.current_mrr),
                "growth_rate": mrr.mrr_growth_rate,
                "net_new": float(mrr.net_new_mrr),
            },
            "customers": {
                "active": customers.active_customers,
                "trial": customers.trial_customers,
                "churn_rate": customers.churn_rate,
                "ltv_cac_ratio": customers.ltv_cac_ratio,
            },
            "revenue": {
                "this_month": float(revenue.revenue_this_month),
                "last_month": float(revenue.revenue_last_month),
                "arpu": float(revenue.average_revenue_per_user),
            },
        }
