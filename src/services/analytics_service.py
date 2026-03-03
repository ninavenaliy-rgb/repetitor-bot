"""Analytics service — dashboard metrics and reporting."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select

from src.database.engine import get_session
from src.database.models import Booking, Payment, User
from src.database.repositories.booking_repo import BookingRepository
from src.database.repositories.payment_repo import PaymentRepository
from src.database.repositories.user_repo import UserRepository


def _progress_bar(pct: int) -> str:
    """Render ASCII progress bar. Example: ▓▓▓▓▓░░░░░ 50%"""
    filled = round(pct / 10)
    return "▓" * filled + "░" * (10 - filled) + f" {pct}%"


@dataclass
class DashboardMetrics:
    """Aggregated metrics for tutor dashboard."""

    total_students: int
    upcoming_lessons: int
    completed_this_month: int
    no_show_count: int
    no_show_rate: float
    engagement_rate: float


@dataclass
class FinancialMetrics:
    """Detailed financial metrics for a given period."""

    period_label: str          # e.g. "Февраль 2026"
    income_paid: Decimal       # sum of paid payments in period
    income_pending: Decimal    # total pending (unpaid) debt
    no_show_count: int         # no-show lessons in period
    losses_no_shows: Decimal   # no_show_count × avg_check
    avg_check: Decimal         # income_paid / completed_count (or 0)
    revenue_forecast: Decimal  # paid + pending + planned × avg_check
    top_student_name: Optional[str]
    top_student_revenue: Decimal
    completed_count: int
    planned_count: int
    week_current: int          # lessons this calendar week
    week_prev: int             # lessons last calendar week


class AnalyticsService:
    """Calculates metrics for the tutor dashboard."""

    async def get_dashboard_metrics(self, tutor_id: uuid.UUID) -> DashboardMetrics:
        """Get all metrics for a tutor's dashboard."""
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            user_repo = UserRepository(session)
            booking_repo = BookingRepository(session)

            total_students = await user_repo.count_by_tutor(tutor_id)

            upcoming = await booking_repo.get_upcoming_by_tutor(
                tutor_id, now, now + timedelta(days=7)
            )
            upcoming_count = len(upcoming)

            completed = await booking_repo.count_by_tutor_status(
                tutor_id, "completed", days=30
            )
            no_shows = await booking_repo.count_by_tutor_status(
                tutor_id, "no_show", days=30
            )
            total_bookings = completed + no_shows
            no_show_rate = (
                (no_shows / total_bookings * 100) if total_bookings > 0 else 0
            )

        return DashboardMetrics(
            total_students=total_students,
            upcoming_lessons=upcoming_count,
            completed_this_month=completed,
            no_show_count=no_shows,
            no_show_rate=round(no_show_rate, 1),
            engagement_rate=0.0,
        )

    async def get_financial_dashboard(
        self,
        tutor_id: uuid.UUID,
        default_lesson_price: Decimal = Decimal("0"),
        since: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        period_label: str = "",
    ) -> FinancialMetrics:
        """Get detailed financial metrics for a period (defaults to current month)."""
        now = datetime.now(timezone.utc)

        if since is None:
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_end is None:
            period_end = now
        if not period_label:
            months_ru = [
                "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
            ]
            period_label = f"{months_ru[since.month]} {since.year}"

        # Week boundaries (Mon–Sun)
        today = now.date()
        monday_this = today - timedelta(days=today.weekday())
        monday_prev = monday_this - timedelta(days=7)
        week_start = datetime(monday_this.year, monday_this.month, monday_this.day, tzinfo=timezone.utc)
        week_end = week_start + timedelta(days=7)
        prev_week_start = datetime(monday_prev.year, monday_prev.month, monday_prev.day, tzinfo=timezone.utc)
        prev_week_end = week_start

        async with get_session() as session:
            pay_repo = PaymentRepository(session)
            booking_repo = BookingRepository(session)

            income_paid = Decimal(await pay_repo.get_paid_sum(tutor_id, since))
            income_pending = Decimal(await pay_repo.get_pending_sum(tutor_id))

            completed_count = await booking_repo.count_by_status_in_range(
                tutor_id, "completed", since, period_end
            )
            no_show_count = await booking_repo.count_by_status_in_range(
                tutor_id, "no_show", since, period_end
            )

            # Planned lessons remaining in period (future only)
            planned_count = await booking_repo.count_planned_in_range(
                tutor_id, now, period_end
            )

            # This week / last week
            this_week = await booking_repo.get_upcoming_by_tutor(tutor_id, week_start, week_end)
            week_current = len(this_week)

            prev_week = await booking_repo.get_upcoming_by_tutor(tutor_id, prev_week_start, prev_week_end)
            week_prev = len(prev_week)

            # Top student by paid revenue in period
            top_result = await session.execute(
                select(
                    Payment.user_id,
                    User.name,
                    func.sum(Payment.amount).label("total"),
                )
                .join(User, Payment.user_id == User.id)
                .where(
                    and_(
                        Payment.tutor_id == tutor_id,
                        Payment.status == "paid",
                        Payment.paid_at >= since,
                    )
                )
                .group_by(Payment.user_id, User.name)
                .order_by(func.sum(Payment.amount).desc())
                .limit(1)
            )
            top_row = top_result.first()

        avg_check = (
            income_paid / completed_count if completed_count > 0 else default_lesson_price
        )
        losses_no_shows = avg_check * no_show_count
        revenue_forecast = income_paid + income_pending + avg_check * planned_count

        return FinancialMetrics(
            period_label=period_label,
            income_paid=income_paid,
            income_pending=income_pending,
            no_show_count=no_show_count,
            losses_no_shows=losses_no_shows,
            avg_check=avg_check,
            revenue_forecast=revenue_forecast,
            top_student_name=top_row.name if top_row else None,
            top_student_revenue=Decimal(top_row.total) if top_row else Decimal("0"),
            completed_count=completed_count,
            planned_count=planned_count,
            week_current=week_current,
            week_prev=week_prev,
        )

    async def get_students_list(
        self, tutor_id: uuid.UUID
    ) -> list[dict]:
        """Get student list with basic info for dashboard."""
        async with get_session() as session:
            user_repo = UserRepository(session)
            students = await user_repo.get_active_by_tutor(tutor_id)

        return [
            {
                "id": str(s.id),
                "name": s.name,
                "cefr_level": s.cefr_level or "—",
                "goal": (s.goal or "—").replace("_", " ").title(),
                "joined": s.created_at.strftime("%Y-%m-%d") if s.created_at else "—",
            }
            for s in students
        ]
