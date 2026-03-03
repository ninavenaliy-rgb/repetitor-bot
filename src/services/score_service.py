"""Academic Score — AI Progress Intelligence (Block A).

Score formula (0-100):
  CEFR component  60% weight  (max 60 pts):  A1=10 … C2=60
  Attendance      up to 15 pts: attendance_rate * 15
  Engagement      up to 12 pts: engagement_rate * 12
  Streak bonus    up to  8 pts: streak // 4, max 8
  Homework        up to  5 pts: hw_count_30d // 4, max 5
  ─────────────────────────────────────────────────────
  Total max = 100

Score is persisted in student_metrics table and logged in score_history
on every triggering event: homework, lesson completion, engagement, placement.
"""

from __future__ import annotations

import uuid
from typing import Optional

# CEFR → base score (60-pt scale, 60% of total)
_CEFR_BASE: dict[str, int] = {
    "A1": 10,
    "A2": 18,
    "B1": 30,
    "B2": 43,
    "C1": 54,
    "C2": 60,
}

# Milestone streak days that trigger a share card
STREAK_MILESTONES = {7, 14, 30, 60, 100}


def compute_score(
    cefr_level: Optional[str],
    streak: int,
    attendance_rate: float = 0.0,
    engagement_rate: float = 0.0,
    hw_count_30d: int = 0,
) -> int:
    """Return Academic Score 0-100."""
    base = _CEFR_BASE.get(cefr_level or "B1", 30)
    attendance_pts = round(min(attendance_rate, 1.0) * 15)
    engagement_pts = round(min(engagement_rate, 1.0) * 12)
    streak_pts = min(streak // 4, 8)
    hw_pts = min(hw_count_30d // 4, 5)
    return min(base + attendance_pts + engagement_pts + streak_pts + hw_pts, 100)


def score_percentile(score: int) -> int:
    """Return percentile rank (how many % of learners are below this score)."""
    if score >= 90:
        return 95
    if score >= 75:
        return 85
    if score >= 58:
        return 70
    if score >= 40:
        return 55
    if score >= 22:
        return 35
    return 20


def build_share_card(
    name: str,
    cefr_level: str | None,
    streak: int,
    ref_link: str,
) -> str:
    """Return the text of the viral share card."""
    score = compute_score(cefr_level, streak)
    pct = score_percentile(score)
    level = cefr_level or "—"

    streak_line = f"🔥 Серия: <b>{streak} дней</b> подряд\n" if streak >= 3 else ""

    return (
        f"🎓 <b>{name}</b> — Academic Score <b>{score}</b>\n\n"
        f"📊 Уровень: <b>{level}</b>\n"
        f"{streak_line}"
        f"👥 Выше <b>{pct}%</b> учеников своего уровня\n\n"
        f"Учу английский с AI-репетитором — без скуки.\n"
        f"Попробуй бесплатно → {ref_link}"
    )


async def update_student_score(user_id: uuid.UUID, source_event: str) -> tuple[int, int]:
    """Recalculate score from live data, persist, return (new_score, delta).

    Call this after: homework check, lesson completion, engagement, placement test.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_, func, select

    from src.database.engine import get_session
    from src.database.models import AIUsage, Booking, EngagementEvent, User
    from src.database.repositories.engagement_repo import EngagementRepository
    from src.database.repositories.metrics_repo import MetricsRepository

    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)

    async with get_session() as session:
        # 1. User cefr_level
        user = await session.get(User, user_id)
        if not user:
            return 0, 0
        cefr = user.cefr_level

        # 2. Streak
        eng_repo = EngagementRepository(session)
        streak = await eng_repo.get_current_streak(user_id)

        # 3. Attendance rate (completed / total bookings last 30d)
        total_q = await session.execute(
            select(func.count(Booking.id)).where(
                and_(
                    Booking.user_id == user_id,
                    Booking.scheduled_at >= since_30d,
                    Booking.status.in_(["completed", "no_show"]),
                )
            )
        )
        total_lessons = total_q.scalar_one() or 0
        if total_lessons:
            done_q = await session.execute(
                select(func.count(Booking.id)).where(
                    and_(
                        Booking.user_id == user_id,
                        Booking.scheduled_at >= since_30d,
                        Booking.status == "completed",
                    )
                )
            )
            attendance_rate = (done_q.scalar_one() or 0) / total_lessons
        else:
            attendance_rate = 0.0

        # 4. Engagement rate (active days / 30)
        engagement_rate = await eng_repo.get_engagement_rate(user_id, days=30)

        # 5. Homework count last 30d
        hw_q = await session.execute(
            select(func.count(AIUsage.id)).where(
                and_(
                    AIUsage.user_id == user_id,
                    AIUsage.usage_type == "homework_check",
                    AIUsage.created_at >= since_30d,
                )
            )
        )
        hw_count_30d = hw_q.scalar_one() or 0

        # 6. Compute new score
        new_score = compute_score(
            cefr_level=cefr,
            streak=streak,
            attendance_rate=attendance_rate,
            engagement_rate=engagement_rate,
            hw_count_30d=hw_count_30d,
        )

        # 7. Persist (upsert metrics + log history)
        metrics_repo = MetricsRepository(session)
        prev = await metrics_repo.get_by_user(user_id)
        prev_score = prev.academic_score if prev else 0
        delta = new_score - prev_score

        await metrics_repo.upsert(
            user_id=user_id,
            academic_score=new_score,
            cefr_level=cefr,
            streak=streak,
            attendance_rate=attendance_rate,
            engagement_rate=engagement_rate,
            hw_count_30d=hw_count_30d,
        )
        await metrics_repo.add_history(user_id, new_score, delta, source_event)
        await session.commit()

    return new_score, delta


def milestone_congrats(streak: int, score: int) -> str:
    """Congratulation text for hitting a streak milestone."""
    messages = {
        7:   "Неделя практики подряд — это уже привычка!",
        14:  "Две недели без пропусков — ты в топ-15% учеников!",
        30:  "Месяц ежедневной практики — это результат, которым стоит гордиться!",
        60:  "Два месяца подряд — редкая дисциплина. Ты в топ-5% по вовлечённости!",
        100: "100 дней практики. Легендарный результат 🏆",
    }
    return messages.get(streak, f"Серия {streak} дней — отличный прогресс!")
