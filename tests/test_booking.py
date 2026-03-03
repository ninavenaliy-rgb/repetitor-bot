"""Tests for booking repository — conflict detection."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Booking, Tutor, User
from src.database.repositories.booking_repo import BookingRepository


@pytest_asyncio.fixture
async def booking_repo(db_session: AsyncSession):
    return BookingRepository(db_session)


@pytest_asyncio.fixture
async def existing_booking(
    db_session: AsyncSession, sample_tutor: Tutor, sample_user: User
) -> Booking:
    """Create a booking at 14:00 for 60 min."""
    booking = Booking(
        tutor_id=sample_tutor.id,
        user_id=sample_user.id,
        scheduled_at=datetime(2026, 3, 1, 14, 0),
        duration_min=60,
        status="planned",
    )
    db_session.add(booking)
    await db_session.flush()
    return booking


class TestBookingConflict:
    """Tests for double-booking prevention."""

    @pytest.mark.asyncio
    async def test_no_conflict_different_time(
        self, booking_repo, sample_tutor, existing_booking
    ):
        """Non-overlapping time should not conflict."""
        conflict = await booking_repo.check_conflict(
            tutor_id=sample_tutor.id,
            start_time=datetime(2026, 3, 1, 16, 0),
            duration_min=60,
        )
        assert conflict is None

    @pytest.mark.asyncio
    async def test_no_conflict_different_day(
        self, booking_repo, sample_tutor, existing_booking
    ):
        """Different day should not conflict."""
        conflict = await booking_repo.check_conflict(
            tutor_id=sample_tutor.id,
            start_time=datetime(2026, 3, 2, 14, 0),
            duration_min=60,
        )
        assert conflict is None

    @pytest.mark.asyncio
    async def test_upcoming_bookings(
        self, booking_repo, sample_tutor, existing_booking
    ):
        """Should return upcoming bookings for tutor."""
        bookings = await booking_repo.get_upcoming_by_tutor(
            tutor_id=sample_tutor.id,
            from_dt=datetime(2026, 3, 1, 0, 0),
            to_dt=datetime(2026, 3, 2, 0, 0),
        )
        assert len(bookings) == 1
        assert bookings[0].id == existing_booking.id
