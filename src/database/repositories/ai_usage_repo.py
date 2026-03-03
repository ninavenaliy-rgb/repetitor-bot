"""Repository for AI usage tracking and rate limiting."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AIUsage


class AIUsageRepository:
    """Data access layer for AI usage tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_today_count(self, user_id: uuid.UUID) -> int:
        """Get number of AI calls made by user today."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.session.execute(
            select(func.count(AIUsage.id)).where(
                and_(
                    AIUsage.user_id == user_id,
                    AIUsage.created_at >= today,
                )
            )
        )
        return result.scalar_one()

    async def record_usage(
        self,
        user_id: uuid.UUID,
        usage_type: str,
        tokens_used: int = 0,
        cost_usd: float | None = None,
    ) -> AIUsage:
        """Record an AI API call."""
        from decimal import Decimal

        usage = AIUsage(
            user_id=user_id,
            usage_type=usage_type,
            tokens_used=tokens_used,
            cost_usd=Decimal(str(cost_usd)) if cost_usd else None,
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_total_cost(self, days: int = 30) -> float:
        """Get total AI cost over the last N days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.session.execute(
            select(func.sum(AIUsage.cost_usd)).where(AIUsage.created_at >= since)
        )
        return float(result.scalar_one() or 0)
