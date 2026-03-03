"""Adaptive placement test service with CEFR scoring."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from config.constants import CEFR_WEIGHTS, CEFRLevel, PLACEMENT_QUESTIONS_COUNT


@dataclass
class PlacementAnswer:
    """Record of a single answer in the placement test."""

    question_id: str
    cefr_level: str
    correct: bool


@dataclass
class PlacementSession:
    """Tracks state of an in-progress placement test."""

    answers: list[PlacementAnswer] = field(default_factory=list)
    current_level: str = CEFRLevel.B1.value
    questions_asked: list[str] = field(default_factory=list)

    @property
    def question_number(self) -> int:
        return len(self.answers) + 1

    @property
    def is_complete(self) -> bool:
        return len(self.answers) >= PLACEMENT_QUESTIONS_COUNT


@dataclass
class PlacementResult:
    """Final result of a placement test."""

    cefr_level: str
    confidence_pct: int
    total_correct: int
    total_questions: int
    suggested_frequency: str


# Level progression order
LEVEL_ORDER = [
    CEFRLevel.A1.value,
    CEFRLevel.A2.value,
    CEFRLevel.B1.value,
    CEFRLevel.B2.value,
    CEFRLevel.C1.value,
    CEFRLevel.C2.value,
]


class PlacementService:
    """Manages adaptive placement test logic."""

    def __init__(self, questions_path: Path | None = None) -> None:
        if questions_path is None:
            questions_path = (
                Path(__file__).resolve().parent.parent.parent
                / "data"
                / "placement_questions.json"
            )
        with open(questions_path, "r", encoding="utf-8") as f:
            self._all_questions: list[dict] = json.load(f)

        # Index questions by level
        self._by_level: dict[str, list[dict]] = {}
        for q in self._all_questions:
            level = q["cefr_level"]
            self._by_level.setdefault(level, []).append(q)

    def get_next_question(self, session: PlacementSession) -> dict | None:
        """Select next adaptive question based on current performance."""
        if session.is_complete:
            return None

        target_level = session.current_level
        candidates = [
            q
            for q in self._by_level.get(target_level, [])
            if q["id"] not in session.questions_asked
        ]

        # If no questions left at this level, try adjacent levels
        if not candidates:
            idx = LEVEL_ORDER.index(target_level)
            for delta in [1, -1, 2, -2]:
                adj_idx = idx + delta
                if 0 <= adj_idx < len(LEVEL_ORDER):
                    adj_level = LEVEL_ORDER[adj_idx]
                    candidates = [
                        q
                        for q in self._by_level.get(adj_level, [])
                        if q["id"] not in session.questions_asked
                    ]
                    if candidates:
                        break

        if not candidates:
            return None

        question = random.choice(candidates)
        session.questions_asked.append(question["id"])
        return question

    def submit_answer(
        self, session: PlacementSession, question: dict, selected_index: int
    ) -> bool:
        """Record an answer and adapt difficulty. Returns True if correct."""
        is_correct = selected_index == question["correct"]

        session.answers.append(
            PlacementAnswer(
                question_id=question["id"],
                cefr_level=question["cefr_level"],
                correct=is_correct,
            )
        )

        # Adapt difficulty
        idx = LEVEL_ORDER.index(session.current_level)
        if is_correct and idx < len(LEVEL_ORDER) - 1:
            session.current_level = LEVEL_ORDER[idx + 1]
        elif not is_correct and idx > 0:
            session.current_level = LEVEL_ORDER[idx - 1]

        return is_correct

    def calculate_result(self, session: PlacementSession) -> PlacementResult:
        """Calculate final CEFR level from all answers."""
        if not session.answers:
            return PlacementResult(
                cefr_level=CEFRLevel.A1.value,
                confidence_pct=0,
                total_correct=0,
                total_questions=0,
                suggested_frequency="3 lessons/week",
            )

        total_correct = sum(1 for a in session.answers if a.correct)
        total_questions = len(session.answers)

        # Weighted scoring: harder questions count more
        weighted_score = 0.0
        max_possible = 0.0
        for answer in session.answers:
            weight = CEFR_WEIGHTS.get(CEFRLevel(answer.cefr_level), 3)
            max_possible += weight
            if answer.correct:
                weighted_score += weight

        ratio = weighted_score / max_possible if max_possible > 0 else 0

        # Map ratio to CEFR band
        if ratio >= 0.85:
            level = CEFRLevel.C2.value
        elif ratio >= 0.72:
            level = CEFRLevel.C1.value
        elif ratio >= 0.58:
            level = CEFRLevel.B2.value
        elif ratio >= 0.42:
            level = CEFRLevel.B1.value
        elif ratio >= 0.25:
            level = CEFRLevel.A2.value
        else:
            level = CEFRLevel.A1.value

        # Confidence based on answer consistency
        correct_levels = [a.cefr_level for a in session.answers if a.correct]
        if correct_levels:
            level_indices = [LEVEL_ORDER.index(l) for l in correct_levels]
            variance = (
                max(level_indices) - min(level_indices)
                if len(level_indices) > 1
                else 0
            )
            confidence = max(60, min(95, 95 - variance * 7))
        else:
            confidence = 50

        # Suggested frequency based on level
        frequency_map = {
            CEFRLevel.A1.value: "3 lessons/week",
            CEFRLevel.A2.value: "2-3 lessons/week",
            CEFRLevel.B1.value: "2 lessons/week",
            CEFRLevel.B2.value: "2 lessons/week",
            CEFRLevel.C1.value: "1-2 lessons/week",
            CEFRLevel.C2.value: "1 lesson/week",
        }

        return PlacementResult(
            cefr_level=level,
            confidence_pct=confidence,
            total_correct=total_correct,
            total_questions=total_questions,
            suggested_frequency=frequency_map.get(level, "2 lessons/week"),
        )
