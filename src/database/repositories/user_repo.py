"""Repository for User CRUD operations."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User


class UserRepository:
    """Data access layer for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Find user by Telegram ID."""
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Find user by primary key."""
        return await self.session.get(User, user_id)

    async def create(self, **kwargs) -> User:
        """Create a new user."""
        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, **kwargs) -> User:
        """Update user fields."""
        for key, value in kwargs.items():
            setattr(user, key, value)
        await self.session.flush()
        return user

    async def get_active_by_tutor(
        self, tutor_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[User]:
        """Get active students for a tutor."""
        result = await self.session.execute(
            select(User)
            .where(User.tutor_id == tutor_id, User.is_active == True)
            .order_by(User.name)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_tutor(self, tutor_id: uuid.UUID) -> int:
        """Count active students for a tutor."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(User.id)).where(
                User.tutor_id == tutor_id, User.is_active == True
            )
        )
        return result.scalar_one()

    async def get_by_student_referral_code(self, code: str) -> Optional[User]:
        """Find student by their referral code (case-insensitive)."""
        result = await self.session.execute(
            select(User).where(User.student_referral_code == code.upper())
        )
        return result.scalar_one_or_none()

    async def count_referrals(self, referrer_id: uuid.UUID) -> int:
        """Count students who registered using this user's referral code."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(User.id)).where(User.referred_by_user_id == referrer_id)
        )
        return result.scalar_one()
