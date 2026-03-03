"""Repository for AI session context (short-term operational memory)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AISession

# Session expires after 30 minutes of inactivity
SESSION_TTL_MINUTES = 30


class AISessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, tutor_id: uuid.UUID) -> Optional[AISession]:
        """Return active (not expired) session for tutor, or None."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(AISession)
            .where(AISession.tutor_id == tutor_id)
            .where(AISession.expires_at > now)
            .order_by(AISession.last_interaction_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, tutor_id: uuid.UUID, context_state: dict
    ) -> AISession:
        """Create or update session with new context_state and refreshed TTL."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=SESSION_TTL_MINUTES)

        ai_session = await self.get_active(tutor_id)
        if ai_session:
            ai_session.context_state = context_state
            ai_session.last_interaction_at = now
            ai_session.expires_at = expires
        else:
            ai_session = AISession(
                id=uuid.uuid4(),
                tutor_id=tutor_id,
                context_state=context_state,
                last_interaction_at=now,
                expires_at=expires,
            )
            self._session.add(ai_session)

        return ai_session

    async def clear(self, tutor_id: uuid.UUID) -> None:
        """Invalidate session after a confirmed action."""
        ai_session = await self.get_active(tutor_id)
        if ai_session:
            now = datetime.now(timezone.utc)
            ai_session.expires_at = now  # expire immediately
