"""Connexion base de données — SQLAlchemy **asynchrone** (Phase 1, Chap 3).

Chaque projet GitSky possède sa propre base (isolation nette : vivre, migrer de
tier, ou être arrêté sans impacter les autres). La session est fournie par
injection de dépendance FastAPI via `get_db`.

Stack async : `create_async_engine` + `async_sessionmaker` + `AsyncSession`.
Driver prod = asyncpg (PostgreSQL) ; dev/tests = aiosqlite (SQLite).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, future=True)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
