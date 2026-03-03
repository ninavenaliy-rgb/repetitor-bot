"""Repository for Booking CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Booking


class BookingRepository:
    """Data access layer for Booking entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, booking_id: uuid.UUID) -> Optional[Booking]:
        """Find booking by primary key."""
        return await self.session.get(Booking, booking_id)

    async def create(self, **kwargs) -> Booking:
        """Create a new booking."""
        booking = Booking(**kwargs)
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def update(self, booking: Booking, **kwargs) -> Booking:
        """Update booking fields."""
        for key, value in kwargs.items():
            setattr(booking, key, value)
        await self.session.flush()
        return booking

    async def check_conflict(
        self,
        tutor_id: uuid.UUID,
        start_time: datetime,
        duration_min: int,
        exclude_booking_id: Optional[uuid.UUID] = None,
    ) -> Optional[Booking]:
        """Check for overlapping bookings. Returns conflicting booking or None."""
        end_time = start_time + timedelta(minutes=duration_min)

        query = (
            select(Booking)
            .where(
                and_(
                    Booking.tutor_id == tutor_id,
                    Booking.status.in_(["planned", "completed"]),
                    Booking.scheduled_at < end_time,
                    Booking.scheduled_at
                    + Booking.duration_min * timedelta(minutes=1)
                    > start_time,
                ),
            )
            .with_for_update()
        )

        if exclude_booking_id:
            query = query.where(Booking.id != exclude_booking_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_upcoming_by_tutor(
        self,
        tutor_id: uuid.UUID,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list[Booking]:
        """Get bookings for a tutor within a date range."""
        result = await self.session.execute(
            select(Booking)
            .where(
                and_(
                    Booking.tutor_id == tutor_id,
                    Booking.scheduled_at >= from_dt,
                    Booking.scheduled_at < to_dt,
                    Booking.status.in_(["planned", "completed"]),
                ),
            )
            .order_by(Booking.scheduled_at)
        )
        return list(result.scalars().all())

    async def get_upcoming_by_user(
        self, user_id: uuid.UUID, from_dt: datetime
    ) -> list[Booking]:
        """Get upcoming bookings for a student."""
        result = await self.session.execute(
            select(Booking)
            .where(
                and_(
                    Booking.user_id == user_id,
                    Booking.scheduled_at >= from_dt,
                    Booking.status == "planned",
                ),
            )
            .order_by(Booking.scheduled_at)
            .limit(10)
        )
        return list(result.scalars().all())

    async def get_needing_reminders(
        self, reminder_window_start: datetime, reminder_window_end: datetime
    ) -> list[Booking]:
        """Get bookings that need reminders sent."""
        result = await self.session.execute(
            select(Booking).where(
                and_(
                    Booking.status == "planned",
                    Booking.scheduled_at >= reminder_window_start,
                    Booking.scheduled_at < reminder_window_end,
                ),
            )
        )
        return list(result.scalars().all())

    async def count_by_tutor_status(
        self, tutor_id: uuid.UUID, status: str, days: int = 30
    ) -> int:
        """Count bookings by status in the last N days."""
        from sqlalchemy import func

        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.session.execute(
            select(func.count(Booking.id)).where(
                and_(
                    Booking.tutor_id == tutor_id,
                    Booking.status == status,
                    Booking.scheduled_at >= since,
                ),
            )
        )
        return result.scalar_one()

    async def count_by_status_in_range(
        self,
        tutor_id: uuid.UUID,
        status: str,
        since: datetime,
        until: datetime,
    ) -> int:
        """Count bookings by status within an explicit date range."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Booking.id)).where(
                and_(
                    Booking.tutor_id == tutor_id,
                    Booking.status == status,
                    Booking.scheduled_at >= since,
                    Booking.scheduled_at < until,
                ),
            )
        )
        return result.scalar_one()

    async def count_planned_in_range(
        self,
        tutor_id: uuid.UUID,
        since: datetime,
        until: datetime,
    ) -> int:
        """Count planned (future) bookings within a date range."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Booking.id)).where(
                and_(
                    Booking.tutor_id == tutor_id,
                    Booking.status == "planned",
                    Booking.scheduled_at >= since,
                    Booking.scheduled_at < until,
                ),
            )
        )
        return result.scalar_one()
