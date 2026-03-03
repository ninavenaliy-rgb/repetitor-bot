"""Repository for Payment CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Payment, User


class PaymentRepository:
    """Data access layer for Payment entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> Payment:
        """Create a new payment record."""
        payment = Payment(**kwargs)
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_id(self, payment_id: uuid.UUID) -> Optional[Payment]:
        return await self.session.get(Payment, payment_id)

    async def mark_paid(self, payment_id: uuid.UUID) -> Optional[Payment]:
        """Mark a payment as paid."""
        payment = await self.get_by_id(payment_id)
        if payment:
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            await self.session.flush()
        return payment

    async def get_by_user(
        self, tutor_id: uuid.UUID, user_id: uuid.UUID, limit: int = 20
    ) -> list[Payment]:
        """Get payments for a specific student."""
        result = await self.session.execute(
            select(Payment)
            .where(and_(Payment.tutor_id == tutor_id, Payment.user_id == user_id))
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_unpaid_by_tutor(self, tutor_id: uuid.UUID) -> list[Payment]:
        """Get all unpaid payments for a tutor."""
        result = await self.session.execute(
            select(Payment)
            .where(and_(Payment.tutor_id == tutor_id, Payment.status == "pending"))
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_debt_summary(
        self, tutor_id: uuid.UUID
    ) -> list[dict]:
        """Get debt summary grouped by student. Returns [{user_id, name, count, total}]."""
        result = await self.session.execute(
            select(
                Payment.user_id,
                User.name,
                func.count(Payment.id).label("count"),
                func.sum(Payment.amount).label("total"),
            )
            .join(User, Payment.user_id == User.id)
            .where(and_(Payment.tutor_id == tutor_id, Payment.status == "pending"))
            .group_by(Payment.user_id, User.name)
            .order_by(func.sum(Payment.amount).desc())
        )
        return [
            {"user_id": row.user_id, "name": row.name, "count": row.count, "total": row.total}
            for row in result.all()
        ]

    async def get_paid_sum(
        self, tutor_id: uuid.UUID, since: datetime
    ) -> Decimal:
        """Total paid amount since a date."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                and_(
                    Payment.tutor_id == tutor_id,
                    Payment.status == "paid",
                    Payment.paid_at >= since,
                )
            )
        )
        return result.scalar_one()

    async def get_pending_sum(self, tutor_id: uuid.UUID) -> Decimal:
        """Total pending (unpaid) amount."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                and_(Payment.tutor_id == tutor_id, Payment.status == "pending")
            )
        )
        return result.scalar_one()
