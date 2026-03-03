"""AI Administrator Service — natural language command interpreter for tutors.

ADDENDUM v1.1 + v1.2 implementation:
- §17 Context Memory Layer
- §18 Multi-Intent Handling
- §19/§32 Recurring Lesson Support
- §20 Natural Language Date Handling (V2 Time Engine)
- §22 Intelligent Confirmation System
- §23 Analytics Logging
- §24 Performance Constraints (temperature ≤ 0.2, max_tokens 800, history ≤ 3)
- §25 Escalation Handling (confidence < 0.7)
- §27 Safety Rules (Strict Mode)
- §28 Scalability: isolated by tutor_id
- §29 Future AI Expansion Hooks (stubs)
- §35 Context Continuation (last_student_referenced)
- §36 lesson_summary intent
- update_student_profile intent (EdTech learning analytics)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger

from config.settings import settings

# ── Performance Constraints (§24) ────────────────────────────────────────────
_TEMPERATURE = 0.2   # §24: temperature ≤ 0.2
_MAX_TOKENS = 800    # §24: enough for compound actions
_MAX_HISTORY = 3     # §24: history ≤ 3 last messages

# ── Weekday names in Russian (§20) ────────────────────────────────────────────
_WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# ── System Prompt V2 — Production Hardened ────────────────────────────────────
# Context is NOT embedded via .format() — it is sent as structured JSON in the user message.
# This avoids escaping issues and makes prompt reusable without recompilation.
_SYSTEM_PROMPT_V2 = """You are TutorSupport Operational AI Agent.

Your ONLY task: parse the input JSON and return a structured JSON intent.
You do NOT execute actions. You do NOT explain. Return JSON only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT FORMAT (you receive this as JSON):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "mode": "text" | "voice",
  "current_datetime": "ISO8601 UTC",
  "timezone": "Europe/Moscow (UTC+3)",
  "current_weekday": "...",
  "students": [{"name": "..."}],
  "existing_lessons": [
    {"student_name": "...", "datetime": "ISO8601", "duration_minutes": 60, "status": "scheduled|completed|cancelled"}
  ],
  "session_context": {
    "last_student_referenced": "...",
    "history": []
  },
  "message": "tutor's text"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPORTED INTENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
book_lesson          — schedule a new lesson (Russian: запиши, поставь, добавь урок)
  entities: student_name, datetime (ISO8601 UTC), duration_min (inherit from last lesson or 60)

reschedule_lesson    — move lesson to another time (Russian: перенеси, передвинь)
  entities: student_name, old_datetime (ISO8601 or null), new_datetime (ISO8601)

cancel_lesson        — cancel/delete a lesson (Russian: отмени, удали, убери)
  entities: student_name, datetime (ISO8601 or null — if null use nearest future lesson), reason (or null)

mark_paid            — record payment (Russian: заплатил, оплатил, оплата)
  entities: student_name, amount (number or null), payment_method (cash/transfer/null)

set_recurring_schedule — create recurring weekly schedule (Russian: каждую неделю, регулярно, по средам)
  entities: student_name, weekday (Mon/Tue/.../Sun), time (HH:MM), duration_min, start_date (ISO8601), end_date (ISO8601 or null)

show_schedule        — show schedule for a period
  entities: date_from (ISO8601), date_to (ISO8601)

show_student         — show student profile
  entities: student_name

add_homework         — assign homework text
  entities: student_name, text

lesson_summary       — record what was covered (Russian: итог урока, прошли, разобрали, занимались)
  entities: student_name, topics_covered (list), weak_areas (list), notes (string or null),
            homework_assigned (list or null), student_mood ("good"|"neutral"|"tired"|null)

update_student_profile — update student learning profile based on lesson pattern (Russian: обнови профиль, запиши слабые места)
  entities: student_name, updated_strengths (list or null), updated_weaknesses (list or null),
            vocabulary_gaps (list or null), grammar_gaps (list or null),
            recommended_focus (list or null), next_lesson_plan (string or null)

compound_action      — multiple actions in one message
  entities: actions (list of {intent, entities} objects)

needs_clarification  — cannot interpret unambiguously (confidence < 0.7)
  entities: clarification_question (string in Russian)

unknown              — no recognizable intent

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIME RESOLUTION RULES (V2 Time Engine):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Resolve relative to current_datetime:
- "завтра" → next day, same time
- "послезавтра" → +2 days
- "в пятницу" → nearest upcoming Friday
- "на следующей неделе" → +7 days
- "через 2 часа" → current_datetime + 2h
- "через неделю в то же время" → find lesson in existing_lessons + 7 days
- "в то же время" / "как обычно" → use last lesson time for this student
- "перенеси на час позже" → find nearest lesson for student + 1h
- "ближайший урок" → use first upcoming in existing_lessons for this student
- "после праздников" → null (clarification_required — need specific date)
- "после Игоря" → find Igor's lesson + its duration
If date missing but time present → assume next occurrence in future.
If ambiguous → needs_clarification.
Always output ISO8601 UTC.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE THRESHOLDS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0.95-1.0  → fully explicit, no assumptions
0.85-0.94 → minor assumption (resolved time phrase from context)
0.70-0.84 → contextual completion (used last_student or existing_lessons)
0.50-0.69 → ambiguous — use needs_clarification
< 0.50    → unknown or multi-meaning — use needs_clarification

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAFETY RULES — STRICT MODE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORBIDDEN:
- Creating students not in the students list
- Inventing dates not derivable from message or context
- Changing duration without explicit instruction
- Assuming payment without explicit mention
All unknown parameters → null (never guess).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY valid JSON. No markdown. No explanation.

Single intent:
{"intent": "book_lesson", "confidence": 0.95, "entities": {"student_name": "Маша", "datetime": "2026-02-27T15:00:00Z", "duration_min": 60}, "needs_confirmation": true}

Compound:
{"intent": "compound_action", "confidence": 0.88, "actions": [{"intent": "cancel_lesson", "entities": {"student_name": "Маша", "datetime": null}}, {"intent": "book_lesson", "entities": {"student_name": "Маша", "datetime": "2026-02-28T15:00:00Z", "duration_min": 60}}], "needs_confirmation": true}

Clarification:
{"intent": "needs_clarification", "confidence": 0.45, "entities": {"clarification_question": "На какое время перенести урок Маши?"}, "needs_confirmation": false}

Rules:
- confidence ∈ [0.0, 1.0]
- needs_confirmation = true for ALL state-changing actions
- confidence < 0.7 → always use needs_clarification
- Return ONLY JSON"""


class AIAdminResult:
    """Parsed result from AI administrator."""

    def __init__(self, data: dict) -> None:
        self.intent: str = data.get("intent", "unknown")
        self.confidence: float = float(data.get("confidence", 0.0))
        self.entities: dict = data.get("entities") or {}
        self.actions: list[dict] = data.get("actions") or []
        self.needs_confirmation: bool = bool(data.get("needs_confirmation", True))
        self.raw: dict = data

    @property
    def is_compound(self) -> bool:
        return self.intent == "compound_action"

    @property
    def needs_escalation(self) -> bool:
        """§25: escalate if confidence < 0.7 or clarification intent."""
        return (
            self.intent in ("needs_clarification", "clarification_required")
            or self.confidence < 0.7
        )

    @property
    def can_soft_confirm(self) -> bool:
        """§22: soft confirmation allowed when confidence > 0.9."""
        return self.confidence > 0.9 and not self.needs_escalation

    @property
    def clarification_question(self) -> Optional[str]:
        return self.entities.get("clarification_question")


class AIAdminService:
    """Interprets tutor's natural language commands via OpenAI API.

    ADDENDUM v1.1 + v1.2. All queries isolated by tutor_id (§28).
    """

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def interpret(
        self,
        text: str,
        tutor_id: uuid.UUID,
        students: list[dict],
        session_context: Optional[dict] = None,
        existing_lessons: Optional[list[dict]] = None,
        mode: str = "text",
    ) -> AIAdminResult:
        """Parse tutor's natural language command and return structured result.

        Args:
            text: tutor's message (text or transcribed voice)
            tutor_id: used for metric logging and data isolation (§28)
            students: list of {name, id} dicts for entity resolution
            session_context: short-term memory from ai_sessions (§17/§35)
            existing_lessons: upcoming/recent lessons for time resolution (V2)
            mode: "text" or "voice" for the AI context

        Returns:
            AIAdminResult with intent, confidence, entities
        """
        now = datetime.now(timezone.utc)
        current_datetime = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        current_weekday = _WEEKDAYS_RU[now.weekday()]

        # §35: Build context hint for last referenced student
        last_student = (session_context or {}).get("last_student_referenced")

        # Format structured JSON input (V2 format — no system prompt variables)
        input_payload = {
            "mode": mode,
            "current_datetime": current_datetime,
            "timezone": "Europe/Moscow (UTC+3)",
            "current_weekday": current_weekday,
            "students": [{"name": s["name"]} for s in students[:50]],
            "existing_lessons": (existing_lessons or [])[:10],
            "session_context": {
                "last_student_referenced": last_student,
                "history": (session_context or {}).get("history", []),
            },
            "message": text,
        }

        # Build message history (§17, §24: history ≤ 3)
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT_V2}]

        if session_context:
            history: list[dict] = session_context.get("history", [])
            for entry in history[-_MAX_HISTORY:]:
                messages.append({"role": entry["role"], "content": entry["content"]})

        messages.append({"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)})

        try:
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
            )
            raw_content = response.choices[0].message.content or "{}"
            data = json.loads(raw_content)
            result = AIAdminResult(data)

        except Exception as e:
            logger.error(f"AI admin interpret error: {e}")
            result = AIAdminResult({
                "intent": "unknown",
                "confidence": 0.0,
                "entities": {},
                "needs_confirmation": False,
            })

        # §23: Log metrics asynchronously (fire-and-forget)
        await self._log_metric(
            tutor_id=tutor_id,
            intent=result.intent,
            confidence=result.confidence,
            raw_input=text,
        )

        return result

    async def _log_metric(
        self,
        tutor_id: uuid.UUID,
        intent: str,
        confidence: float,
        raw_input: str,
    ) -> None:
        """§23: Analytics logging — non-blocking."""
        try:
            from src.database.engine import get_session
            from src.database.repositories.ai_metrics_repo import AIMetricsRepository
            async with get_session() as session:
                repo = AIMetricsRepository(session)
                await repo.log(
                    tutor_id=tutor_id,
                    intent=intent,
                    confidence=confidence,
                    raw_input=raw_input,
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"AI metric logging failed (non-critical): {e}")

    def build_confirmation_text(self, result: AIAdminResult) -> str:
        """§22: Generate human-readable confirmation message."""
        e = result.entities
        intent = result.intent

        # book_lesson (also aliased as create_lesson for V2 compatibility)
        if intent in ("book_lesson", "create_lesson"):
            student = e.get("student_name", "?")
            dt = _fmt_dt(e.get("datetime"))
            dur = e.get("duration_min")
            dur_text = f", {dur} мин" if dur else ""
            return f"Записать <b>{student}</b> на <b>{dt}</b>{dur_text}. Всё верно?"

        if intent == "reschedule_lesson":
            student = e.get("student_name", "?")
            new_dt = _fmt_dt(e.get("new_datetime"))
            return f"Перенести урок <b>{student}</b> на <b>{new_dt}</b>. Всё верно?"

        if intent == "cancel_lesson":
            student = e.get("student_name", "?")
            dt = _fmt_dt(e.get("datetime"))
            reason = e.get("reason")
            reason_text = f"\nПричина: {reason}" if reason else ""
            return f"Отменить урок <b>{student}</b>{' ' + dt if dt else ''}.{reason_text}\nВсё верно?"

        if intent == "mark_paid":
            student = e.get("student_name", "?")
            amount = e.get("amount")
            method = e.get("payment_method")
            amount_text = f" {amount}₽" if amount else ""
            method_text = f" ({method})" if method else ""
            return f"Отметить оплату{amount_text}{method_text} от <b>{student}</b>. Всё верно?"

        # set_recurring_schedule (also create_recurring for V2 compatibility)
        if intent in ("set_recurring_schedule", "create_recurring"):
            student = e.get("student_name", "?")
            weekday = e.get("weekday", "?")
            time = e.get("time", "?")
            dur = e.get("duration_min")
            dur_text = f", {dur} мин" if dur else ""
            return (
                f"Создать расписание для <b>{student}</b>:\n"
                f"Каждый <b>{weekday}</b> в <b>{time}</b>{dur_text}. Всё верно?"
            )

        if intent == "add_homework":
            student = e.get("student_name", "?")
            hw_text = e.get("text", "")
            preview = hw_text[:80] + ("..." if len(hw_text) > 80 else "")
            return f"Задать домашнее задание <b>{student}</b>:\n<i>{preview}</i>\nВсё верно?"

        if intent == "lesson_summary":
            student = e.get("student_name", "?")
            topics = e.get("topics_covered") or []
            weak = e.get("weak_areas") or []
            mood = e.get("student_mood")
            topics_text = ", ".join(topics) if topics else "—"
            weak_text = ", ".join(weak) if weak else "—"
            mood_text = f"\nНастроение: {mood}" if mood else ""
            return (
                f"Сохранить итог урока <b>{student}</b>:\n"
                f"Темы: {topics_text}\n"
                f"Трудности: {weak_text}{mood_text}\nВсё верно?"
            )

        if intent == "update_student_profile":
            student = e.get("student_name", "?")
            weaknesses = e.get("updated_weaknesses") or []
            focus = e.get("recommended_focus") or []
            w_text = ", ".join(weaknesses) if weaknesses else "—"
            f_text = ", ".join(focus) if focus else "—"
            return (
                f"Обновить профиль <b>{student}</b>:\n"
                f"Слабые места: {w_text}\n"
                f"Рекомендуемый фокус: {f_text}\nВсё верно?"
            )

        if intent == "compound_action":
            lines = ["Выполнить несколько действий:"]
            for i, action in enumerate(result.actions, 1):
                sub = AIAdminResult({**action, "confidence": 1.0, "needs_confirmation": False})
                lines.append(f"{i}. {self.build_confirmation_text(sub).rstrip('Всё верно?').strip()}")
            lines.append("\nВсё верно?")
            return "\n".join(lines)

        return "Выполнить действие. Всё верно?"

    # ── §29 Future AI Expansion Hooks (stubs) ─────────────────────────────────

    async def suggest_load_optimization(self, tutor_id: uuid.UUID) -> Optional[str]:
        """§29: Hook — load optimization suggestions. Not implemented in MVP."""
        return None

    async def detect_cancellation_pattern(self, tutor_id: uuid.UUID) -> Optional[str]:
        """§29: Hook — cancellation pattern detection. Not implemented in MVP."""
        return None

    async def student_retention_alert(self, tutor_id: uuid.UUID) -> Optional[str]:
        """§29: Hook — student retention alerts. Not implemented in MVP."""
        return None


def _fmt_dt(dt_str: Optional[str]) -> str:
    """Format ISO8601 datetime to human-readable Russian format."""
    if not dt_str:
        return ""
    try:
        from datetime import timedelta
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        moscow = dt + timedelta(hours=3)
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        wd = weekdays[moscow.weekday()]
        return f"{moscow.strftime('%d.%m')} ({wd}) {moscow.strftime('%H:%M')}"
    except Exception:
        return dt_str
