"""Repository for referral commissions and stats."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ReferralCommission, Tutor

COMMISSION_RATE = Decimal("0.15")  # 15%


class ReferralRepository:
    """Data access layer for referral program."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_commission(
        self,
        referrer_id: uuid.UUID,
        referred_id: uuid.UUID,
        payment_amount: Decimal,
    ) -> ReferralCommission:
        """Record a referral commission (15% of payment_amount)."""
        commission = payment_amount * COMMISSION_RATE
        record = ReferralCommission(
            referrer_id=referrer_id,
            referred_id=referred_id,
            payment_amount=payment_amount,
            commission=commission,
        )
        self.session.add(record)

        # Add to referrer's balance
        await self.session.execute(
            update(Tutor)
            .where(Tutor.id == referrer_id)
            .values(referral_balance=Tutor.referral_balance + commission)
        )
        await self.session.flush()
        return record

    async def get_referral_count(self, referrer_id: uuid.UUID) -> int:
        """Count tutors referred by this tutor."""
        result = await self.session.execute(
            select(func.count()).where(Tutor.referred_by_id == referrer_id)
        )
        return result.scalar_one() or 0

    async def get_total_commission(self, referrer_id: uuid.UUID) -> Decimal:
        """Total commission earned by referrer."""
        result = await self.session.execute(
            select(func.sum(ReferralCommission.commission)).where(
                ReferralCommission.referrer_id == referrer_id
            )
        )
        return result.scalar_one() or Decimal("0")

    async def get_referrals(self, referrer_id: uuid.UUID) -> list[Tutor]:
        """Get list of tutors referred by this tutor."""
        result = await self.session.execute(
            select(Tutor).where(Tutor.referred_by_id == referrer_id)
        )
        return list(result.scalars().all())

    async def get_by_referral_code(self, code: str) -> Optional[Tutor]:
        """Find tutor by referral code."""
        result = await self.session.execute(
            select(Tutor).where(Tutor.referral_code == code.upper())
        )
        return result.scalar_one_or_none()
