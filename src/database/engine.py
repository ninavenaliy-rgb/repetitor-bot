"""Async database engine — supports both PostgreSQL and SQLite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings

_is_sqlite = settings.database_url.startswith("sqlite")

if _is_sqlite:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Verify connection and auto-create tables (SQLite only)."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

    if _is_sqlite:
        # Auto-create all tables for local SQLite development
        from src.database.models import Base  # noqa: F401
        import src.database.models_subscription  # noqa: F401 — register subscription models

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Seed required data (plans) — works for both SQLite and PostgreSQL
    from src.database.seeds import seed_subscription_plans

    async with async_session_factory() as session:
        await seed_subscription_plans(session)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
