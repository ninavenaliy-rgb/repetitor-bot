"""Engagement service — Word of the Day, streaks, daily content."""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from config.constants import CEFRLevel, EngagementEventType
from src.database.engine import get_session
from src.database.models import EngagementEvent
from src.database.repositories.engagement_repo import EngagementRepository

# Minimum level for Word of the Day — never send A1/A2/B1
_LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
_MIN_WOD_LEVEL = "B2"

# Module-level cache: word bank is read from disk once and reused across all
# EngagementService instances (avoids repeated file I/O in Celery tasks).
_word_bank_cache: dict[str, list[dict]] | None = None
_word_bank_default_path = (
    Path(__file__).resolve().parent.parent.parent / "data" / "word_bank.json"
)


def _load_word_bank(path: Path) -> dict[str, list[dict]]:
    global _word_bank_cache
    if _word_bank_cache is None:
        with open(path, "r", encoding="utf-8") as f:
            _word_bank_cache = json.load(f)
    return _word_bank_cache


def _effective_level(cefr_level: str) -> str:
    """Return at least B2 for WoD regardless of actual level."""
    if cefr_level in _LEVEL_ORDER:
        idx = _LEVEL_ORDER.index(cefr_level)
        min_idx = _LEVEL_ORDER.index(_MIN_WOD_LEVEL)
        return _LEVEL_ORDER[max(idx, min_idx)]
    return _MIN_WOD_LEVEL


class EngagementService:
    """Business logic for daily engagement and streak tracking."""

    def __init__(self, word_bank_path: Path | None = None) -> None:
        path = word_bank_path or _word_bank_default_path
        self._word_bank: dict[str, list[dict]] = _load_word_bank(path)

    def get_word_of_day(self, cefr_level: str = "B2") -> dict:
        """Get a random word at B2+ level from the static word bank."""
        level = _effective_level(cefr_level)
        words = self._word_bank.get(level) or self._word_bank.get("B2", [])
        return random.choice(words) if words else {
            "word": "resilient", "phonetic": "/rɪˈzɪliənt/",
            "definition": "able to recover quickly from difficulties",
            "example": "Stay resilient in the face of challenges.",
            "etymology": "Latin resilire — to spring back",
            "academic_note": "Harvard psychology studies on grit",
        }

    async def get_word_of_day_ai(self, cefr_level: str = "B2") -> dict:
        """Generate today's word via GPT. Falls back to static bank on error."""
        from src.services.ai_service import AIService
        level = _effective_level(cefr_level)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            ai = AIService()
            return await ai.generate_word_of_day(level, date_str)
        except Exception as e:
            logger.warning(f"AI word generation failed, using static bank: {e}")
            return self.get_word_of_day(level)

    async def get_streak(self, user_id: uuid.UUID) -> int:
        """Calculate current streak for a user."""
        async with get_session() as session:
            repo = EngagementRepository(session)
            return await repo.get_current_streak(user_id)

    async def record_interaction(
        self,
        user_id: uuid.UUID,
        event_type: str,
        completed: bool = True,
    ) -> int:
        """Record an engagement event and return updated streak count."""
        async with get_session() as session:
            repo = EngagementRepository(session)

            # Check if already completed today
            today_event = await repo.get_today_event(user_id, event_type)
            if today_event and today_event.completed:
                return today_event.streak_day

            # Calculate streak
            streak = await repo.get_current_streak(user_id)
            new_streak = streak + 1 if completed else 0

            if today_event:
                await repo.update(
                    today_event, completed=completed, streak_day=new_streak
                )
            else:
                await repo.create(
                    user_id=user_id,
                    event_type=event_type,
                    completed=completed,
                    streak_day=new_streak,
                )

            return new_streak

    def format_word_of_day(self, word_data: dict, streak: int) -> str:
        """Форматирование сообщения «Слово дня» с академическим контекстом."""
        streak_emoji = "🔥" if streak >= 3 else ("✨" if streak >= 1 else "")
        streak_text = f"\n{streak_emoji} Серия: <b>{streak}</b> дней подряд!" if streak > 0 else ""

        etymology = word_data.get("etymology", "")
        academic_note = word_data.get("academic_note", "")

        etymology_block = f"\n\n📖 <i>Этимология:</i> {etymology}" if etymology else ""
        academic_block = f"\n🎓 <i>{academic_note}</i>" if academic_note else ""

        return (
            f"📚 <b>Слово дня</b>\n\n"
            f"<b>{word_data['word']}</b>  {word_data['phonetic']}\n"
            f"<i>{word_data['definition']}</i>\n\n"
            f"💬 <b>Пример:</b>\n<i>«{word_data['example']}»</i>"
            f"{etymology_block}"
            f"{academic_block}"
            f"{streak_text}\n\n"
            f"Составьте своё предложение с этим словом! 💪"
        )
