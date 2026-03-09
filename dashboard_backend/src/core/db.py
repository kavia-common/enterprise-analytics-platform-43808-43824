from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.postgres_url,
        pool_pre_ping=True,
        future=True,
    )


ENGINE: AsyncEngine = _create_engine()
ASYNC_SESSION_FACTORY: async_sessionmaker[AsyncSession] = async_sessionmaker(
    ENGINE, expire_on_commit=False, autoflush=False
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context-managed transaction scope."""
    async with ASYNC_SESSION_FACTORY() as session:
        try:
            yield session
        finally:
            await session.close()


# PUBLIC_INTERFACE
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession."""
    async with ASYNC_SESSION_FACTORY() as session:
        yield session
