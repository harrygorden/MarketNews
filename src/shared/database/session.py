"""
Async SQLAlchemy engine and session management helpers.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from shared.config import Settings, get_settings
from shared.database.models import Base

logger = logging.getLogger(__name__)


def create_engine_from_settings(settings: Settings | None = None) -> AsyncEngine:
    """
    Create an async engine using the provided settings or default environment settings.
    """

    settings = settings or get_settings()
    logger.debug("Creating async engine for %s", settings.DATABASE_URL)
    return create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True, future=True)


def get_session_maker(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    """
    Return an async session factory bound to the provided engine (or default engine).
    """

    engine = engine or create_engine_from_settings()
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session(engine: AsyncEngine | None = None) -> AsyncIterator[AsyncSession]:
    """
    Context-managed async session generator.
    """

    session_maker = get_session_maker(engine)
    async with session_maker() as session:
        yield session


async def init_models(engine: AsyncEngine | None = None) -> None:
    """
    Create all database tables defined in the ORM models.
    """

    engine = engine or create_engine_from_settings()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

