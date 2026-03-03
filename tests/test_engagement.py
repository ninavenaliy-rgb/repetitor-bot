"""Tests for engagement service — streaks and word of the day."""

from __future__ import annotations

import pytest

from src.services.engagement_service import EngagementService


@pytest.fixture
def service():
    return EngagementService()


class TestEngagementService:
    """Tests for Word of the Day and streak logic."""

    def test_word_of_day_returns_data(self, service):
        """Should return a word with all required fields."""
        word = service.get_word_of_day("B1")
        assert "word" in word
        assert "phonetic" in word
        assert "definition" in word
        assert "example" in word

    def test_word_of_day_default_level(self, service):
        """Should fall back to B1 for unknown levels."""
        word = service.get_word_of_day("X9")
        assert "word" in word

    def test_format_word_no_streak(self, service):
        """Format should work with zero streak."""
        word = {"word": "test", "phonetic": "/test/", "definition": "a trial", "example": "This is a test."}
        text = service.format_word_of_day(word, 0)
        assert "test" in text
        assert "Серия" not in text

    def test_format_word_with_streak(self, service):
        """Format should include streak info."""
        word = {"word": "test", "phonetic": "/test/", "definition": "a trial", "example": "This is a test."}
        text = service.format_word_of_day(word, 5)
        assert "5 дней" in text

    def test_all_levels_have_words(self, service):
        """Every CEFR level should return words."""
        for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            word = service.get_word_of_day(level)
            assert word is not None
            assert len(word["word"]) > 0
