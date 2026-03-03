"""Repository for StudentMetrics and ScoreHistory."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ScoreHistory, StudentMetrics


class MetricsRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user(self, user_id: uuid.UUID) -> Optional[StudentMetrics]:
        result = await self.session.execute(
            select(StudentMetrics).where(StudentMetrics.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: uuid.UUID, **kwargs) -> StudentMetrics:
        """Create or update StudentMetrics row for user."""
        metrics = await self.get_by_user(user_id)
        if metrics is None:
            metrics = StudentMetrics(user_id=user_id, **kwargs)
            self.session.add(metrics)
        else:
            for key, value in kwargs.items():
                setattr(metrics, key, value)
            metrics.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return metrics

    async def add_history(
        self, user_id: uuid.UUID, score: int, delta: int, source_event: str
    ) -> ScoreHistory:
        entry = ScoreHistory(
            user_id=user_id,
            score=score,
            delta=delta,
            source_event=source_event,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_recent_history(
        self, user_id: uuid.UUID, limit: int = 10
    ) -> list[ScoreHistory]:
        result = await self.session.execute(
            select(ScoreHistory)
            .where(ScoreHistory.user_id == user_id)
            .order_by(ScoreHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
