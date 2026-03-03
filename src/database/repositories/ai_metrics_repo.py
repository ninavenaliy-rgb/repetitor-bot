"""Repository for AI command analytics (section 23 of ADDENDUM v1.1)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AIMetric


class AIMetricsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        tutor_id: uuid.UUID,
        intent: Optional[str],
        confidence: Optional[float],
        raw_input: Optional[str] = None,
        error_type: Optional[str] = None,
        was_correct: Optional[bool] = None,
    ) -> AIMetric:
        """Record one AI interpretation event."""
        metric = AIMetric(
            id=uuid.uuid4(),
            tutor_id=tutor_id,
            intent=intent,
            confidence=confidence,
            was_correct=was_correct,
            error_type=error_type,
            raw_input=raw_input[:500] if raw_input else None,
        )
        self._session.add(metric)
        return metric
