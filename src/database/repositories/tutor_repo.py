"""Repository for Tutor CRUD operations."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Tutor


class TutorRepository:
    """Data access layer for Tutor entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Tutor]:
        """Find tutor by Telegram ID."""
        result = await self.session.execute(
            select(Tutor).where(Tutor.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, tutor_id: uuid.UUID) -> Optional[Tutor]:
        """Find tutor by primary key."""
        return await self.session.get(Tutor, tutor_id)

    async def create(self, **kwargs) -> Tutor:
        """Create a new tutor."""
        tutor = Tutor(**kwargs)
        self.session.add(tutor)
        await self.session.flush()
        return tutor

    async def get_by_invite_token(self, token: str) -> Optional[Tutor]:
        """Find tutor by invite token."""
        result = await self.session.execute(
            select(Tutor).where(Tutor.invite_token == token)
        )
        return result.scalar_one_or_none()

    async def update(self, tutor: Tutor, **kwargs) -> Tutor:
        """Update tutor fields."""
        for key, value in kwargs.items():
            setattr(tutor, key, value)
        await self.session.flush()
        return tutor
