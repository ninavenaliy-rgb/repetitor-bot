"""Tests for AI service — response parsing and feedback formatting."""

from __future__ import annotations

import pytest

from src.services.ai_service import AIService, Correction, HomeworkFeedback, VocabSuggestion


class TestHomeworkFeedback:
    """Tests for feedback model and formatting."""

    def test_parse_valid_json(self):
        """Should parse valid feedback JSON."""
        data = {
            "corrections": [
                {"original": "he go", "corrected": "he goes", "explanation": "third person -s"}
            ],
            "vocabulary_suggestions": [
                {"original": "good", "suggested": "excellent", "reason": "stronger word"}
            ],
            "estimated_band": "B1",
            "overall_comment": "Good effort!",
        }
        feedback = HomeworkFeedback(**data)
        assert feedback.estimated_band == "B1"
        assert len(feedback.corrections) == 1
        assert feedback.corrections[0].corrected == "he goes"

    def test_empty_feedback(self):
        """Should handle empty corrections/suggestions."""
        feedback = HomeworkFeedback(
            corrections=[],
            vocabulary_suggestions=[],
            estimated_band="A2",
            overall_comment="No errors found!",
        )
        assert len(feedback.corrections) == 0

    def test_format_feedback(self):
        """Should format feedback into readable text."""
        service = AIService.__new__(AIService)
        feedback = HomeworkFeedback(
            corrections=[
                Correction(
                    original="he go", corrected="he goes", explanation="third person"
                )
            ],
            vocabulary_suggestions=[
                VocabSuggestion(
                    original="good", suggested="excellent", reason="more precise"
                )
            ],
            estimated_band="B1",
            overall_comment="Keep it up!",
        )
        text = service.format_feedback(feedback)
        assert "he goes" in text
        assert "B1" in text
        assert "excellent" in text

    def test_format_no_corrections(self):
        """Should handle format with no corrections gracefully."""
        service = AIService.__new__(AIService)
        feedback = HomeworkFeedback(
            corrections=[],
            vocabulary_suggestions=[],
            estimated_band="C1",
            overall_comment="Perfect!",
        )
        text = service.format_feedback(feedback)
        assert "C1" in text
        assert "Corrections" not in text
