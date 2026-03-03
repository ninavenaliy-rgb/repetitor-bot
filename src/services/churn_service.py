"""Churn Risk AI — Block B.

Heuristic churn scoring (Phase 1, no ML):
  Condition 1: attendance_rate  < 0.60  (missed 40%+ of lessons in 30d)
  Condition 2: engagement_7d   < 3     (fewer than 3 active days last week)
  Condition 3: score_delta_30d < 2     (score barely moved in a month)

Risk levels:
  HIGH   — 2+ conditions met  →  churn_probability ≈ 0.65–0.85
  MEDIUM — 1 condition met    →  churn_probability ≈ 0.35–0.50
  LOW    — 0 conditions met   →  churn_probability ≈ 0.10–0.20

Score prediction (linear extrapolation):
  growth_rate = score_delta_30d / 30  (pts per day)
  predicted_N_weeks = current_score + growth_rate * N * 7
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class ChurnResult:
    risk_level: str          # "HIGH" | "MEDIUM" | "LOW"
    churn_probability: float # 0.0 – 1.0
    reasons: list[str]       # human-readable reasons
    attendance_rate: float
    engagement_7d: int       # active days last 7 days
    score_delta_30d: int     # score change in 30 days
    predicted_4w: Optional[int] = None
    predicted_8w: Optional[int] = None
    predicted_12w: Optional[int] = None


async def assess_churn_risk(user_id: uuid.UUID) -> ChurnResult:
    """Compute churn risk and score predictions for a student."""
    from sqlalchemy import and_, func, select

    from src.database.engine import get_session
    from src.database.models import Booking, EngagementEvent
    from src.database.repositories.engagement_repo import EngagementRepository
    from src.database.repositories.metrics_repo import MetricsRepository

    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)
    since_7d = now - timedelta(days=7)

    async with get_session() as session:
        # 1. Attendance rate (30d)
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
            attendance_rate = 1.0  # no lessons — no churn signal from attendance

        # 2. Engagement last 7 days (distinct active days)
        eng_q = await session.execute(
            select(func.count(func.distinct(func.date(EngagementEvent.created_at)))).where(
                and_(
                    EngagementEvent.user_id == user_id,
                    EngagementEvent.completed == True,
                    EngagementEvent.created_at >= since_7d,
                )
            )
        )
        engagement_7d = eng_q.scalar_one() or 0

        # 3. Score delta (30d) from history
        metrics_repo = MetricsRepository(session)
        history = await metrics_repo.get_recent_history(user_id, limit=60)
        current_score = history[0].score if history else 0

        # Find score ~30 days ago
        score_30d_ago = current_score
        for entry in reversed(history):
            if entry.created_at <= since_30d:
                score_30d_ago = entry.score
                break
        score_delta_30d = current_score - score_30d_ago

    # ── Risk assessment ──────────────────────────────────────────────────────
    reasons: list[str] = []
    conditions_met = 0

    if total_lessons > 0 and attendance_rate < 0.60:
        conditions_met += 1
        pct = round(attendance_rate * 100)
        reasons.append(f"Посещаемость {pct}% — пропускает каждый 2-й урок")

    if engagement_7d < 3:
        conditions_met += 1
        reasons.append(f"Активен только {engagement_7d} из 7 дней на прошлой неделе")

    if len(history) >= 2 and score_delta_30d < 2:
        conditions_met += 1
        reasons.append(f"Прогресс score за месяц: +{score_delta_30d} (стагнация)")

    if conditions_met >= 2:
        risk_level = "HIGH"
        churn_probability = 0.65 + min(conditions_met - 2, 1) * 0.15
    elif conditions_met == 1:
        risk_level = "MEDIUM"
        churn_probability = 0.35
    else:
        risk_level = "LOW"
        churn_probability = 0.10

    # ── Score prediction (linear extrapolation) ──────────────────────────────
    growth_per_day = score_delta_30d / 30 if len(history) >= 2 else 0.1

    def predict(weeks: int) -> int:
        return max(0, min(100, round(current_score + growth_per_day * weeks * 7)))

    return ChurnResult(
        risk_level=risk_level,
        churn_probability=round(churn_probability, 2),
        reasons=reasons,
        attendance_rate=round(attendance_rate, 2),
        engagement_7d=engagement_7d,
        score_delta_30d=score_delta_30d,
        predicted_4w=predict(4),
        predicted_8w=predict(8),
        predicted_12w=predict(12),
    )


async def get_at_risk_students(tutor_id: uuid.UUID) -> list[dict]:
    """Return list of HIGH/MEDIUM churn risk students for a tutor."""
    from sqlalchemy import select

    from src.database.engine import get_session
    from src.database.models import User

    async with get_session() as session:
        result = await session.execute(
            select(User).where(
                User.tutor_id == tutor_id,
                User.is_active == True,
            )
        )
        students = list(result.scalars().all())

    at_risk = []
    for student in students:
        try:
            churn = await assess_churn_risk(student.id)
            if churn.risk_level in ("HIGH", "MEDIUM"):
                at_risk.append({
                    "user_id": student.id,
                    "telegram_id": student.telegram_id,
                    "name": student.name or "Ученик",
                    "risk_level": churn.risk_level,
                    "churn_probability": churn.churn_probability,
                    "reasons": churn.reasons,
                    "predicted_8w": churn.predicted_8w,
                })
        except Exception:
            pass

    # Sort: HIGH first, then by probability desc
    at_risk.sort(key=lambda x: (-int(x["risk_level"] == "HIGH"), -x["churn_probability"]))
    return at_risk


def format_churn_for_tutor(name: str, result: ChurnResult) -> str:
    """Format churn report for tutor notification."""
    risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
    emoji = risk_emoji.get(result.risk_level, "⚪")

    reasons_text = "\n".join(f"  • {r}" for r in result.reasons) if result.reasons else "  • Нет явных сигналов"

    pred_text = ""
    if result.predicted_8w is not None:
        trend = "📈" if result.predicted_8w > (result.predicted_4w or 0) else "📉"
        pred_text = (
            f"\n\n📊 <b>Прогноз score:</b>\n"
            f"  4 недели: {result.predicted_4w}\n"
            f"  8 недель: {result.predicted_8w} {trend}\n"
            f"  12 недель: {result.predicted_12w}"
        )

    return (
        f"{emoji} <b>{name}</b> — риск отвала {result.risk_level}\n"
        f"Вероятность: <b>{round(result.churn_probability * 100)}%</b>\n\n"
        f"<b>Причины:</b>\n{reasons_text}"
        f"{pred_text}"
    )
