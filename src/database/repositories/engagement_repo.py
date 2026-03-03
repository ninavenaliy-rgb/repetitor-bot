"""Repository for EngagementEvent operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import EngagementEvent


class EngagementRepository:
    """Data access layer for engagement tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> EngagementEvent:
        """Create a new engagement event."""
        event = EngagementEvent(**kwargs)
        self.session.add(event)
        await self.session.flush()
        return event

    async def update(self, event: EngagementEvent, **kwargs) -> EngagementEvent:
        """Update an engagement event."""
        for key, value in kwargs.items():
            setattr(event, key, value)
        await self.session.flush()
        return event

    async def get_today_event(
        self, user_id: uuid.UUID, event_type: str
    ) -> Optional[EngagementEvent]:
        """Get today's event for a user and type."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        result = await self.session.execute(
            select(EngagementEvent).where(
                and_(
                    EngagementEvent.user_id == user_id,
                    EngagementEvent.event_type == event_type,
                    EngagementEvent.created_at >= today,
                    EngagementEvent.created_at < tomorrow,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_current_streak(self, user_id: uuid.UUID) -> int:
        """Calculate current consecutive-day streak."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Get the most recent completed event
        result = await self.session.execute(
            select(EngagementEvent)
            .where(
                and_(
                    EngagementEvent.user_id == user_id,
                    EngagementEvent.completed == True,
                )
            )
            .order_by(EngagementEvent.created_at.desc())
            .limit(1)
        )
        last_event = result.scalar_one_or_none()

        if not last_event:
            return 0

        last_date = last_event.created_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # If last activity was before yesterday, streak is broken
        if last_date < today - timedelta(days=1):
            return 0

        return last_event.streak_day

    async def get_engagement_rate(
        self, user_id: uuid.UUID, days: int = 30
    ) -> float:
        """Calculate engagement rate (active days / total days) for a period."""
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.session.execute(
            select(func.count(func.distinct(func.date(EngagementEvent.created_at))))
            .where(
                and_(
                    EngagementEvent.user_id == user_id,
                    EngagementEvent.completed == True,
                    EngagementEvent.created_at >= since,
                )
            )
        )
        active_days = result.scalar_one() or 0
        return active_days / days if days > 0 else 0
