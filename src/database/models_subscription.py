"""Subscription billing models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models import Base


class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    TRIAL = "trial"
    ACTIVE = "active"
    GRACE = "grace"  # Grace period after failed payment
    CANCELED = "canceled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"


class TransactionStatus(str, Enum):
    """Transaction status enum."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransactionType(str, Enum):
    """Transaction type enum."""
    CHARGE = "charge"
    REFUND = "refund"
    PRORATION = "proration"
    ADJUSTMENT = "adjustment"


class SubscriptionEventType(str, Enum):
    """Subscription event types."""
    CREATED = "created"
    TRIAL_STARTED = "trial_started"
    TRIAL_ENDED = "trial_ended"
    ACTIVATED = "activated"
    UPGRADED = "upgraded"
    DOWNGRADED = "downgraded"
    RENEWED = "renewed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PAYMENT_FAILED = "payment_failed"
    GRACE_STARTED = "grace_started"
    GRACE_ENDED = "grace_ended"


class SubscriptionPlan(Base):
    """Subscription plan (START, GROWTH, SCALE)."""

    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    description_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Pricing
    price_rub_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_usd_monthly: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price_eur_monthly: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Features (JSON for flexibility)
    features: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Limits
    max_students: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_ai_checks_per_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Meta
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="plan")

    def get_price(self, currency: str) -> Decimal:
        """Get price for currency."""
        currency_map = {
            "RUB": self.price_rub_monthly,
            "USD": self.price_usd_monthly,
            "EUR": self.price_eur_monthly,
        }
        price = currency_map.get(currency.upper())
        if price is None:
            raise ValueError(f"Price not set for currency {currency}")
        return price

    def has_feature(self, feature_key: str) -> bool:
        """Check if plan has feature."""
        return self.features.get(feature_key, False) is True

    @property
    def name(self) -> str:
        """Get plan name (defaults to Russian)."""
        return self.name_ru

    @property
    def price_rub(self) -> Decimal:
        """Alias for price_rub_monthly."""
        return self.price_rub_monthly


class Subscription(Base):
    """User subscription."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tutor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscription_plans.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SubscriptionStatus.TRIAL.value)

    # Dates
    trial_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    grace_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Billing
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Payment provider
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Extra metadata (renamed from metadata to avoid SQLAlchemy conflict)
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", back_populates="subscriptions")
    history: Mapped[list["SubscriptionHistory"]] = relationship("SubscriptionHistory", back_populates="subscription")
    transactions: Mapped[list["BillingTransaction"]] = relationship("BillingTransaction", back_populates="subscription")
    usage: Mapped[list["UsageTracking"]] = relationship("UsageTracking", back_populates="subscription")

    @property
    def is_active(self) -> bool:
        """Check if subscription is active."""
        return self.status in (SubscriptionStatus.TRIAL.value, SubscriptionStatus.ACTIVE.value, SubscriptionStatus.GRACE.value)

    @property
    def is_in_grace_period(self) -> bool:
        """Check if in grace period."""
        if self.status != SubscriptionStatus.GRACE.value:
            return False
        if not self.grace_period_end:
            return False
        return datetime.now(timezone.utc) < self.grace_period_end

    @property
    def days_until_expiry(self) -> int:
        """Days until subscription expires."""
        if not self.current_period_end:
            return 0
        delta = self.current_period_end - datetime.now(timezone.utc)
        return max(0, delta.days)


class SubscriptionHistory(Base):
    """Subscription change history."""

    __tablename__ = "subscription_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    tutor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    new_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)

    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)

    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="history")


class BillingTransaction(Base):
    """Billing transaction (charge/refund/proration)."""

    __tablename__ = "billing_transactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    tutor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), nullable=False)

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TransactionStatus.PENDING.value)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    # Provider
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_payment_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    succeeded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Error handling
    failure_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="transactions")


class UsageTracking(Base):
    """Track feature usage per billing period."""

    __tablename__ = "usage_tracking"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    tutor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tutors.id", ondelete="CASCADE"), nullable=False)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Usage counters
    students_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_checks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bookings_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reminders_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="usage")
