"""FastAPI dependencies for the web dashboard."""

from __future__ import annotations

from typing import Optional

from src.database.engine import get_session
from src.database.models import Tutor
from src.database.repositories.tutor_repo import TutorRepository


async def get_tutor_by_token(token: str) -> Optional[Tutor]:
    """Validate dashboard access token and return tutor.

    For MVP, token is the tutor's telegram_id.
    In production, replace with proper JWT or API key auth.
    """
    if not token:
        return None

    try:
        telegram_id = int(token)
    except ValueError:
        return None

    async with get_session() as session:
        repo = TutorRepository(session)
        return await repo.get_by_telegram_id(telegram_id)
