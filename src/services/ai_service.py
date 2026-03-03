"""AI service — homework checking and content generation via OpenAI."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from config.constants import AIUsageType
from config.settings import settings
from src.database.engine import get_session
from src.database.repositories.ai_usage_repo import AIUsageRepository
from src.utils.exceptions import RateLimitExceededError


class Correction(BaseModel):
    original: str
    corrected: str
    explanation: str


class VocabSuggestion(BaseModel):
    original: str
    suggested: str
    reason: str


class IELTSScores(BaseModel):
    task_achievement: float = 0.0
    coherence_cohesion: float = 0.0
    lexical_resource: float = 0.0
    grammatical_range: float = 0.0
    overall_band: float = 0.0


class EGEScores(BaseModel):
    communication_task: int = 0   # 0-3
    text_organization: int = 0    # 0-3
    vocabulary: int = 0           # 0-3
    grammar: int = 0              # 0-3
    spelling: int = 0             # 0-2
    total: int = 0                # 0-14


class HomeworkFeedback(BaseModel):
    corrections: list[Correction] = Field(default_factory=list)
    vocabulary_suggestions: list[VocabSuggestion] = Field(default_factory=list)
    estimated_band: str = "B1"
    overall_comment: str = ""
    strengths: list[str] = Field(default_factory=list)
    topics_to_study: list[str] = Field(default_factory=list)
    tutor_note: str = ""
    # Goal-specific
    goal_type: str = "general"
    ielts_scores: Optional[IELTSScores] = None
    ege_scores: Optional[EGEScores] = None
    business_rating: str = ""
    register_issues: list[str] = Field(default_factory=list)


# ─── GENERAL prompt ─────────────────────────────────────────────────────────
_PROMPT_GENERAL = """You are an expert English tutor reviewing student homework.
Student's CEFR level: {cefr_level}.

Analyze the text and return ONLY valid JSON:
{{
  "corrections": [{{"original":"...","corrected":"...","explanation":"...in Russian"}}],
  "vocabulary_suggestions": [{{"original":"...","suggested":"...","reason":"...in Russian"}}],
  "overall_comment": "2-3 sentences in Russian: strengths and focus areas",
  "strengths": ["strength 1 in Russian","strength 2 in Russian"],
  "topics_to_study": ["topic 1 in Russian","topic 2 in Russian","topic 3 in Russian"],
  "tutor_note": "2-3 sentences in Russian for tutor: error patterns, next lesson recommendations"
}}
Rules: up to 7 corrections, up to 4 vocab suggestions, 2-3 strengths, 3-5 topics.
All text in Russian. Return ONLY JSON."""

# ─── IELTS prompt ────────────────────────────────────────────────────────────
_PROMPT_IELTS = """You are a certified IELTS examiner reviewing a student's writing task.
Target band: {cefr_level} equivalent.

Evaluate strictly using official IELTS Writing Band Descriptors (4 criteria, each 0-9 in 0.5 steps):
- Task Achievement: addresses all parts, position clear, relevant examples
- Coherence & Cohesion: logical progression, paragraphing, cohesive devices
- Lexical Resource: vocabulary range, precision, collocations, spelling
- Grammatical Range & Accuracy: sentence variety, tense control, error frequency

Return ONLY valid JSON:
{{
  "corrections": [{{"original":"...","corrected":"...","explanation":"rule in Russian"}}],
  "vocabulary_suggestions": [{{"original":"...","suggested":"...","reason":"why in Russian"}}],
  "overall_comment": "2-3 sentences in Russian: what to do to raise band score",
  "strengths": ["IELTS strength in Russian"],
  "topics_to_study": ["specific IELTS skill to practice in Russian"],
  "tutor_note": "Professional note in Russian: band breakdown, which criterion holds score down, drill recommendations",
  "ielts_scores": {{
    "task_achievement": 6.5,
    "coherence_cohesion": 7.0,
    "lexical_resource": 6.0,
    "grammatical_range": 6.5,
    "overall_band": 6.5
  }}
}}
Be precise with band scores. Overall = average of 4 criteria rounded to nearest 0.5.
All Russian text in Russian. Return ONLY JSON."""

# ─── ЕГЭ prompt ──────────────────────────────────────────────────────────────
_PROMPT_EGE = """You are an expert checking English writing for the Russian ЕГЭ (state exam).
Student's level: {cefr_level}.

ЕГЭ Writing section criteria (Раздел «Письмо», задание 37 — развёрнутое письменное высказывание):

К1 — Решение коммуникативной задачи (0-3 балла):
  3 = все аспекты раскрыты полностью, стиль соответствует
  2 = все аспекты, но не все подробно; незначительные стилевые погрешности
  1 = только некоторые аспекты
  0 = коммуникативная задача не выполнена

К2 — Организация текста (0-3 балла):
  3 = чёткая структура: вступление, основная часть, заключение; абзацы; средства связи
  2 = структура в целом правильная, небольшие погрешности
  1 = структура нарушена, недостаточно средств связи
  0 = без структуры

К3 — Лексика (0-3 балла):
  3 = разнообразная лексика, соответствующая уровню, без ошибок
  2 = достаточный словарный запас, 1-2 лексические ошибки
  1 = ограниченный словарный запас, 3-4 ошибки
  0 = множество ошибок

К4 — Грамматика (0-3 балла):
  3 = разнообразные конструкции, 0-1 негрубая ошибка
  2 = несколько типов конструкций, 2-3 ошибки
  1 = простые конструкции, 4-5 ошибок
  0 = множество ошибок

К5 — Орфография и пунктуация (0-2 балла):
  2 = нет ошибок или 1 негрубая
  1 = 2-3 ошибки
  0 = 4+ ошибки

Return ONLY valid JSON:
{{
  "corrections": [{{"original":"...","corrected":"...","explanation":"критерий ЕГЭ + правило на русском"}}],
  "vocabulary_suggestions": [{{"original":"...","suggested":"...","reason":"на русском"}}],
  "overall_comment": "2-3 предложения на русском: что помогает и что снижает баллы ЕГЭ",
  "strengths": ["сильная сторона по критериям ЕГЭ на русском"],
  "topics_to_study": ["что отработать для ЕГЭ на русском"],
  "tutor_note": "Рекомендация репетитору на русском: какой критерий снижает итог, что отрабатывать на следующем уроке",
  "ege_scores": {{
    "communication_task": 2,
    "text_organization": 3,
    "vocabulary": 2,
    "grammar": 3,
    "spelling": 2,
    "total": 12
  }}
}}
All Russian text in Russian. Return ONLY JSON."""

# ─── Business prompt ─────────────────────────────────────────────────────────
_PROMPT_BUSINESS = """You are a business communication coach reviewing professional English writing.
Student's CEFR level: {cefr_level}. Goal: Business English.

Evaluate for:
- Professional register and tone (formal vs informal)
- Business vocabulary (industry terms, collocations, hedging language)
- Email/memo/report structure (if applicable): subject line, opening, body, CTA, closing
- Conciseness and clarity (no redundancy, clear calls to action)
- Diplomatic language (negative news, requests, complaints)
- C-suite / international business communication standards

Return ONLY valid JSON:
{{
  "corrections": [{{"original":"...","corrected":"...","explanation":"business rule in Russian"}}],
  "vocabulary_suggestions": [{{"original":"...","suggested":"...","reason":"business context in Russian"}}],
  "overall_comment": "2-3 sentences in Russian: professional communication assessment",
  "strengths": ["business strength in Russian"],
  "topics_to_study": ["business skill to develop in Russian"],
  "tutor_note": "Note in Russian for tutor: communication issues, recommended business English drills",
  "business_rating": "Suitable for professional use",
  "register_issues": ["informal phrase or error that breaks business register"]
}}
business_rating options: "Suitable for C-suite", "Suitable for professional use",
"Suitable for internal use only", "Needs significant improvement".
Up to 7 corrections, 4 vocab suggestions. Return ONLY JSON."""


def _get_prompt(goal: str, cefr_level: str) -> str:
    """Select appropriate system prompt based on student goal."""
    if goal in ("ielts", "toefl"):
        return _PROMPT_IELTS.format(cefr_level=cefr_level)
    elif goal == "oge_ege":
        return _PROMPT_EGE.format(cefr_level=cefr_level)
    elif goal == "business":
        return _PROMPT_BUSINESS.format(cefr_level=cefr_level)
    else:
        return _PROMPT_GENERAL.format(cefr_level=cefr_level)


class AIService:
    """Manages OpenAI API calls for homework checking and content generation."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def check_homework(
        self,
        text: str,
        cefr_level: str,
        user_id: uuid.UUID,
        goal: str = "general",
    ) -> HomeworkFeedback:
        """Analyze student text with goal-specific prompt."""
        # Rate limit check + usage recording share one DB session
        async with get_session() as session:
            repo = AIUsageRepository(session)
            today_count = await repo.get_today_count(user_id)
            if today_count >= settings.ai_rate_limit_per_user:
                raise RateLimitExceededError(
                    f"Daily limit of {settings.ai_rate_limit_per_user} AI calls reached"
                )

            prompt = _get_prompt(goal, cefr_level)

            try:
                response = await self.client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=2000,
                    temperature=0.3,
                )

                content = response.choices[0].message.content
                tokens_used = response.usage.total_tokens if response.usage else 0
                cost_usd = tokens_used * 0.0000003

                await repo.record_usage(
                    user_id=user_id,
                    usage_type=AIUsageType.HOMEWORK_CHECK.value,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                )

            except RateLimitExceededError:
                raise
            except Exception as e:
                logger.error(f"AI homework check error: {e}")
                return HomeworkFeedback(
                    goal_type=goal,
                    overall_comment="Не удалось проанализировать текст. Попробуйте ещё раз.",
                )

        try:
            data = json.loads(content)
            data["goal_type"] = goal

            # Parse nested goal-specific objects
            if "ielts_scores" in data and data["ielts_scores"]:
                data["ielts_scores"] = IELTSScores(**data["ielts_scores"])
            if "ege_scores" in data and data["ege_scores"]:
                data["ege_scores"] = EGEScores(**data["ege_scores"])

            return HomeworkFeedback.model_validate(data)
        except Exception as e:
            logger.error(f"AI response parse error: {e}")
            return HomeworkFeedback(
                goal_type=goal,
                overall_comment="Не удалось разобрать ответ AI. Попробуйте ещё раз.",
            )

    async def transcribe_voice(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        import io
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            transcript = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
            )
            return transcript.text
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return ""

    async def check_pronunciation(
        self, transcript: str, cefr_level: str, user_id: uuid.UUID
    ) -> str:
        await self.check_rate_limit(user_id)
        system_prompt = (
            f"You are an English speaking coach. The student (level {cefr_level}) "
            "sent a voice message. Here is the transcript. "
            "Give brief feedback (2-4 sentences in Russian) on: vocabulary used, "
            "possible grammar issues visible in the text, fluency suggestions. "
            "Be encouraging."
        )
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript},
                ],
                max_tokens=400,
                temperature=0.5,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Pronunciation check error: {e}")
            return "Не удалось проанализировать запись. Попробуйте ещё раз."

    async def generate_lesson_plan(
        self,
        student_name: str,
        cefr_level: str,
        goal: str,
        recent_topics: str,
        duration_min: int,
        tutor_id: uuid.UUID,
    ) -> str:
        system_prompt = (
            "You are an experienced English tutor assistant. "
            "Create a detailed lesson plan in Russian. "
            "Format it clearly with sections: Разминка, Основная часть, Практика, Домашнее задание. "
            "Be specific and practical."
        )
        user_msg = (
            f"Студент: {student_name}\n"
            f"Уровень: {cefr_level}\n"
            f"Цель: {goal}\n"
            f"Недавние темы: {recent_topics}\n"
            f"Длительность урока: {duration_min} минут\n\n"
            "Составь план урока."
        )
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=800,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Lesson plan generation error: {e}")
            raise

    async def generate_word_of_day(self, cefr_level: str, date_str: str) -> dict:
        """Generate an academic Word of the Day using GPT.

        Args:
            cefr_level: student level (B2/C1/C2)
            date_str: YYYY-MM-DD used as seed for variety
        Returns dict with keys: word, phonetic, definition, example, etymology, academic_note
        """
        system_prompt = (
            "You are an English vocabulary professor at Harvard University. "
            "Your specialty is academic vocabulary from Harvard, Stanford, Oxford curricula "
            "and classical philosophy (Socrates, Plato, Aristotle).\n\n"
            f"Generate a single vocabulary entry for a student at {cefr_level} CEFR level.\n"
            "Requirements:\n"
            "- Choose a word at B2 level or above (never A1/A2/B1)\n"
            "- Prefer academic, intellectual, or philosophical vocabulary\n"
            "- Etymology must include the Latin/Greek root meaning\n"
            "- Academic note: mention a specific university course, philosopher, or publication where this word appears\n"
            "- Example sentence must be vivid and demonstrate real academic use\n\n"
            "Return ONLY valid JSON:\n"
            '{"word":"...","phonetic":"/IPA/","definition":"...","example":"...","etymology":"...","academic_note":"..."}'
        )
        user_msg = f"Today's date: {date_str}. Generate the word of the day for level {cefr_level}."

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=300,
                temperature=0.8,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            # Validate required keys
            required = {"word", "phonetic", "definition", "example", "etymology", "academic_note"}
            if not required.issubset(data.keys()):
                raise ValueError(f"Missing keys: {required - data.keys()}")
            return data
        except Exception as e:
            logger.error(f"Word of the day generation error: {e}")
            raise

    def format_feedback_student(self, feedback: HomeworkFeedback, lang: str = "ru") -> str:
        """Полный отчёт для ученика (с goal-специфичными блоками)."""
        from src.bot.locales import t

        parts = [f"<b>{t(lang, 'hw_title')}</b>"]

        # Goal-specific header block
        if feedback.goal_type in ("ielts", "toefl") and feedback.ielts_scores:
            sc = feedback.ielts_scores
            parts.append(
                f"\n🎓 <b>IELTS Band Scores</b>\n"
                f"  Task Achievement: <b>{sc.task_achievement}</b>\n"
                f"  Coherence & Cohesion: <b>{sc.coherence_cohesion}</b>\n"
                f"  Lexical Resource: <b>{sc.lexical_resource}</b>\n"
                f"  Grammatical Range: <b>{sc.grammatical_range}</b>\n"
                f"  ⭐ Overall Band: <b>{sc.overall_band}</b>"
            )
        elif feedback.goal_type == "oge_ege" and feedback.ege_scores:
            sc = feedback.ege_scores
            parts.append(
                f"\n📝 <b>Баллы ЕГЭ</b>\n"
                f"  К1 Коммуникативная задача: <b>{sc.communication_task}/3</b>\n"
                f"  К2 Организация текста: <b>{sc.text_organization}/3</b>\n"
                f"  К3 Лексика: <b>{sc.vocabulary}/3</b>\n"
                f"  К4 Грамматика: <b>{sc.grammar}/3</b>\n"
                f"  К5 Орфография: <b>{sc.spelling}/2</b>\n"
                f"  ⭐ Итого: <b>{sc.total}/14</b>"
            )
        elif feedback.goal_type == "business" and feedback.business_rating:
            parts.append(f"\n💼 <b>Бизнес-оценка:</b> {feedback.business_rating}")
            if feedback.register_issues:
                parts.append("<b>Нарушения регистра:</b>")
                for issue in feedback.register_issues[:3]:
                    parts.append(f"  ⚠️ {issue}")

        # Сильные стороны
        if feedback.strengths:
            parts.append(f"\n✅ <b>{t(lang, 'hw_strengths')}</b>")
            for s in feedback.strengths:
                parts.append(f"  • {s}")

        # Исправления
        if feedback.corrections:
            parts.append(f"\n❌ <b>{t(lang, 'hw_corrections')}</b>")
            for i, c in enumerate(feedback.corrections, 1):
                parts.append(
                    f'{i}. <s>{c.original}</s> → <b>{c.corrected}</b>\n'
                    f'   <i>{c.explanation}</i>'
                )

        # Словарный запас
        if feedback.vocabulary_suggestions:
            parts.append(f"\n📚 <b>{t(lang, 'hw_vocab')}</b>")
            for v in feedback.vocabulary_suggestions:
                parts.append(f"  {v.original} → <b>{v.suggested}</b>\n   <i>{v.reason}</i>")

        # Темы для изучения
        if feedback.topics_to_study:
            parts.append(f"\n🎯 <b>{t(lang, 'hw_topics')}</b>")
            for topic in feedback.topics_to_study:
                parts.append(f"  • {topic}")

        # Итог
        if feedback.overall_comment:
            parts.append(f"💬 {feedback.overall_comment}")

        return "\n".join(parts)

    def format_tutor_report(self, feedback: HomeworkFeedback, student_name: str) -> str:
        """Краткий отчёт репетитору о домашней работе ученика."""
        goal_label = {
            "ielts": "IELTS", "toefl": "IELTS/TOEFL",
            "oge_ege": "ЕГЭ", "business": "Business",
            "general": "Общий",
        }.get(feedback.goal_type, "Общий")

        parts = [
            f"📋 <b>Домашнее задание: {student_name}</b>",
            f"🎯 Цель: {goal_label}",
        ]

        # Goal-specific score summary
        if feedback.goal_type in ("ielts", "toefl") and feedback.ielts_scores:
            sc = feedback.ielts_scores
            parts.append(
                f"⭐ IELTS: <b>{sc.overall_band}</b> "
                f"(TA:{sc.task_achievement} CC:{sc.coherence_cohesion} "
                f"LR:{sc.lexical_resource} GR:{sc.grammatical_range})"
            )
        elif feedback.goal_type == "oge_ege" and feedback.ege_scores:
            sc = feedback.ege_scores
            parts.append(
                f"⭐ ЕГЭ: <b>{sc.total}/14</b> "
                f"(К1:{sc.communication_task} К2:{sc.text_organization} "
                f"К3:{sc.vocabulary} К4:{sc.grammar} К5:{sc.spelling})"
            )
        elif feedback.goal_type == "business" and feedback.business_rating:
            parts.append(f"💼 {feedback.business_rating}")
        else:
            parts.append(f"📊 Уровень текста: <b>{feedback.estimated_band}</b>")

        parts.append(f"❌ Ошибок: <b>{len(feedback.corrections)}</b>")

        if feedback.topics_to_study:
            topics = ", ".join(feedback.topics_to_study[:3])
            parts.append(f"🎯 Темы для отработки: {topics}")

        if feedback.tutor_note:
            parts.append(f"\n💡 <b>Рекомендация AI:</b>\n{feedback.tutor_note}")

        if feedback.corrections:
            parts.append("\n<b>Ключевые ошибки:</b>")
            for c in feedback.corrections[:3]:
                parts.append(f"  • <s>{c.original}</s> → <b>{c.corrected}</b>")

        return "\n".join(parts)

    def format_feedback(self, feedback: HomeworkFeedback) -> str:
        return self.format_feedback_student(feedback, lang="ru")

    async def check_homework_from_image(
        self,
        image_bytes: bytes,
        cefr_level: str,
        user_id: uuid.UUID,
        goal: str = "general",
    ) -> HomeworkFeedback:
        """Проверка домашнего задания из изображения через GPT-4o Vision."""
        import base64
        await self.check_rate_limit(user_id)

        prompt = _get_prompt(goal, cefr_level)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Check this homework image. Extract all visible text and analyze it:",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=2000,
                temperature=0.3,
            )

            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            cost_usd = tokens_used * 0.000005  # gpt-4o pricing

            async with get_session() as session:
                repo = AIUsageRepository(session)
                await repo.record_usage(
                    user_id=user_id,
                    usage_type=AIUsageType.HOMEWORK_CHECK.value,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                )

            data = json.loads(content)
            data["goal_type"] = goal

            if "ielts_scores" in data and data["ielts_scores"]:
                data["ielts_scores"] = IELTSScores(**data["ielts_scores"])
            if "ege_scores" in data and data["ege_scores"]:
                data["ege_scores"] = EGEScores(**data["ege_scores"])

            return HomeworkFeedback.model_validate(data)

        except RateLimitExceededError:
            raise
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"AI image homework check error: {e}")
            return HomeworkFeedback(
                goal_type=goal,
                overall_comment="Не удалось проанализировать изображение. Попробуйте ещё раз.",
            )
