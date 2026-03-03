"""Booking service — orchestrates slot availability, double-booking protection, and calendar sync."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger

from config.constants import DEFAULT_LESSON_DURATION_MIN
from src.database.engine import get_session
from src.database.models import Booking
from src.database.repositories.booking_repo import BookingRepository
from src.services.calendar_service import GoogleCalendarService
from src.utils.exceptions import SlotConflictError


class BookingService:
    """Business logic for lesson booking."""

    def __init__(self) -> None:
        self.calendar = GoogleCalendarService()

    async def get_available_slots(
        self,
        tutor_id: uuid.UUID,
        calendar_id: str,
        date: datetime,
        duration_min: int = DEFAULT_LESSON_DURATION_MIN,
    ) -> list[datetime]:
        """Get available slots considering both calendar and existing bookings."""
        # Get slots from Google Calendar
        calendar_slots = await self.calendar.get_free_slots(
            calendar_id=calendar_id,
            date=date,
            slot_duration_min=duration_min,
        )

        # Filter out slots already booked in our DB
        day_start = date.replace(hour=0, minute=0, second=0)
        day_end = day_start + timedelta(days=1)

        async with get_session() as session:
            repo = BookingRepository(session)
            existing = await repo.get_upcoming_by_tutor(tutor_id, day_start, day_end)

        booked_times: set[datetime] = set()
        for booking in existing:
            # Normalize to UTC-naive for consistent comparison with calendar slots
            bt = booking.scheduled_at
            if bt.tzinfo is not None:
                bt = bt.astimezone(timezone.utc).replace(tzinfo=None)
            booked_times.add(bt)

        available = [
            s for s in calendar_slots
            if s.replace(tzinfo=None) not in booked_times
        ]

        # Filter out past slots
        now = datetime.now(timezone.utc)
        available = [s for s in available if s > now + timedelta(hours=1)]

        return available

    async def create_booking(
        self,
        tutor_id: uuid.UUID,
        user_id: uuid.UUID,
        calendar_id: str,
        scheduled_at: datetime,
        duration_min: int = DEFAULT_LESSON_DURATION_MIN,
        topic: str | None = None,
    ) -> Booking:
        """Create a booking with double-booking protection and calendar sync."""
        async with get_session() as session:
            repo = BookingRepository(session)

            # Double-booking check with row-level lock
            conflict = await repo.check_conflict(tutor_id, scheduled_at, duration_min)
            if conflict:
                raise SlotConflictError(
                    f"Slot conflict with booking {conflict.id} "
                    f"at {conflict.scheduled_at}"
                )

            # Create booking in DB first — if this fails we don't orphan a calendar event
            booking = await repo.create(
                tutor_id=tutor_id,
                user_id=user_id,
                scheduled_at=scheduled_at,
                duration_min=duration_min,
                status="planned",
                confirmation_status="pending",
                topic=topic,
                google_event_id=None,
            )

            # Then sync to Google Calendar (non-critical — booking is already saved)
            try:
                event_id = await self.calendar.create_event(
                    calendar_id=calendar_id,
                    summary="English Lesson",
                    start_time=scheduled_at,
                    duration_min=duration_min,
                    description=topic or "",
                )
                await repo.update(booking, google_event_id=event_id)
            except Exception as cal_err:
                logger.warning(
                    f"Calendar sync failed for booking {booking.id}: {cal_err}"
                )

            logger.info(
                f"Booking created: {booking.id} at {scheduled_at}",
                extra={"tutor_id": str(tutor_id), "user_id": str(user_id)},
            )
            return booking

    async def cancel_booking(self, booking_id: uuid.UUID, calendar_id: str) -> Booking:
        """Cancel a booking and remove calendar event."""
        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(booking_id)

            if not booking:
                raise ValueError(f"Booking {booking_id} not found")

            # Remove calendar event
            if booking.google_event_id:
                await self.calendar.delete_event(calendar_id, booking.google_event_id)

            await repo.update(booking, status="cancelled")
            logger.info(f"Booking cancelled: {booking_id}")
            return booking

    async def confirm_booking(self, booking_id: uuid.UUID) -> Booking:
        """Mark booking as confirmed by student."""
        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(booking_id)
            if not booking:
                raise ValueError(f"Booking {booking_id} not found")
            await repo.update(booking, confirmation_status="confirmed")
            return booking

    async def complete_booking(
        self,
        booking_id: uuid.UUID,
        topic: str | None = None,
        homework: str | None = None,
        notes: str | None = None,
    ) -> Booking:
        """Mark booking as completed with optional lesson notes."""
        async with get_session() as session:
            repo = BookingRepository(session)
            booking = await repo.get_by_id(booking_id)
            if not booking:
                raise ValueError(f"Booking {booking_id} not found")

            update_data = {"status": "completed"}
            if topic:
                update_data["topic"] = topic
            if homework:
                update_data["homework"] = homework
            if notes:
                update_data["notes"] = notes

            await repo.update(booking, **update_data)
            return booking
