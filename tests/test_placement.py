"""Tests for placement test service."""

from __future__ import annotations

import pytest

from src.services.placement_service import (
    LEVEL_ORDER,
    PlacementAnswer,
    PlacementResult,
    PlacementService,
    PlacementSession,
)


@pytest.fixture
def service():
    """Create placement service with default questions."""
    return PlacementService()


class TestPlacementService:
    """Tests for adaptive placement test logic."""

    def test_get_first_question(self, service):
        """First question should be returned successfully."""
        session = PlacementSession()
        question = service.get_next_question(session)
        assert question is not None
        assert "question" in question
        assert "options" in question
        assert "correct" in question

    def test_questions_not_repeated(self, service):
        """Questions should not repeat during a session."""
        session = PlacementSession()
        seen_ids = set()
        for _ in range(12):
            q = service.get_next_question(session)
            if q is None:
                break
            assert q["id"] not in seen_ids
            seen_ids.add(q["id"])
            service.submit_answer(session, q, q["correct"])

    def test_difficulty_increases_on_correct(self, service):
        """Correct answer should increase difficulty level."""
        session = PlacementSession()
        session.current_level = "B1"
        q = service.get_next_question(session)
        service.submit_answer(session, q, q["correct"])
        # Level should have moved up
        assert LEVEL_ORDER.index(session.current_level) >= LEVEL_ORDER.index("B1")

    def test_difficulty_decreases_on_wrong(self, service):
        """Wrong answer should decrease difficulty level."""
        session = PlacementSession()
        session.current_level = "B2"
        q = service.get_next_question(session)
        # Submit wrong answer
        wrong = (q["correct"] + 1) % len(q["options"])
        service.submit_answer(session, q, wrong)
        assert LEVEL_ORDER.index(session.current_level) <= LEVEL_ORDER.index("B2")

    def test_all_correct_gives_high_level(self, service):
        """All correct answers should result in C1/C2."""
        session = PlacementSession()
        for _ in range(12):
            q = service.get_next_question(session)
            if q is None:
                break
            service.submit_answer(session, q, q["correct"])

        result = service.calculate_result(session)
        assert result.cefr_level in ("C1", "C2")
        assert result.confidence_pct >= 60

    def test_all_wrong_gives_low_level(self, service):
        """All wrong answers should result in A1/A2."""
        session = PlacementSession()
        for _ in range(12):
            q = service.get_next_question(session)
            if q is None:
                break
            wrong = (q["correct"] + 1) % len(q["options"])
            service.submit_answer(session, q, wrong)

        result = service.calculate_result(session)
        assert result.cefr_level in ("A1", "A2")

    def test_empty_session_gives_a1(self, service):
        """Empty session should return A1 with 0 confidence."""
        session = PlacementSession()
        result = service.calculate_result(session)
        assert result.cefr_level == "A1"
        assert result.confidence_pct == 0

    def test_session_completion(self, service):
        """Session should mark as complete after 12 questions."""
        session = PlacementSession()
        for _ in range(12):
            q = service.get_next_question(session)
            if q is None:
                break
            service.submit_answer(session, q, q["correct"])

        assert session.is_complete

    def test_result_has_frequency(self, service):
        """Result should include suggested lesson frequency."""
        session = PlacementSession()
        for _ in range(12):
            q = service.get_next_question(session)
            if q is None:
                break
            service.submit_answer(session, q, q["correct"])

        result = service.calculate_result(session)
        assert "lesson" in result.suggested_frequency.lower()
