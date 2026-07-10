"""Base de données du landing collector (async, autonome).

Service minimal : pas d'Alembic, les tables sont créées au démarrage. URL via
LANDING_DB_URL (PostgreSQL partagé en prod ; SQLite en dev/tests).
"""

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.environ.get("LANDING_DB_URL", "sqlite+aiosqlite:///./leads.db")

engine = create_async_engine(DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_session():
    async with SessionLocal() as session:
        yield session


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
