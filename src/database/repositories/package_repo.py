"""Repository for LessonPackage CRUD operations."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import LessonPackage


class PackageRepository:
    """Data access layer for LessonPackage entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> LessonPackage:
        """Create a new lesson package."""
        pkg = LessonPackage(**kwargs)
        self.session.add(pkg)
        await self.session.flush()
        return pkg

    async def get_by_id(self, package_id: uuid.UUID) -> Optional[LessonPackage]:
        """Find package by primary key."""
        return await self.session.get(LessonPackage, package_id)

    async def get_active_for_user(
        self, tutor_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[LessonPackage]:
        """Return the active package for a student."""
        result = await self.session.execute(
            select(LessonPackage)
            .where(
                LessonPackage.tutor_id == tutor_id,
                LessonPackage.user_id == user_id,
                LessonPackage.status == "active",
            )
            .order_by(LessonPackage.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def deduct_lesson(self, package_id: uuid.UUID) -> Optional[LessonPackage]:
        """Decrement lessons_remaining. Mark exhausted if 0. Returns updated package."""
        pkg = await self.get_by_id(package_id)
        if not pkg:
            return None
        if pkg.lessons_remaining > 0:
            pkg.lessons_remaining -= 1
        if pkg.lessons_remaining == 0:
            pkg.status = "exhausted"
        await self.session.flush()
        return pkg

    async def cancel(self, package_id: uuid.UUID) -> None:
        """Cancel a package."""
        await self.session.execute(
            update(LessonPackage)
            .where(LessonPackage.id == package_id)
            .values(status="cancelled")
        )
        await self.session.flush()
