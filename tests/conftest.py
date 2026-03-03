"""Test fixtures and configuration."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base, Booking, Tutor, User


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    """Create async engine with in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide a test database session."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_tutor(db_session: AsyncSession) -> Tutor:
    """Create a sample tutor for testing."""
    tutor = Tutor(
        telegram_id=100001,
        name="Test Tutor",
        subjects="English",
    )
    db_session.add(tutor)
    await db_session.flush()
    return tutor


@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession, sample_tutor: Tutor) -> User:
    """Create a sample student user for testing."""
    user = User(
        telegram_id=200001,
        name="Test Student",
        tutor_id=sample_tutor.id,
        cefr_level="B1",
        goal="general",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def mock_openai():
    """Mock OpenAI AsyncOpenAI client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"corrections": [], "vocabulary_suggestions": [], "estimated_band": "B1", "overall_comment": "Good work!"}'
            )
        )
    ]
    mock_response.usage = MagicMock(total_tokens=500)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client
