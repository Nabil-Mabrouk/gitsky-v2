"""Modèle core `User` / `UserRole` (Phase 1, incrément 3).

Vérifie les défauts (role=user, is_active=True, created_at posé par la base) et
la contrainte d'unicité de l'email. Chaque test crée son propre moteur async
in-memory (StaticPool = une seule connexion partagée) pour rester isolé de
`app.core.database.engine`.
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402


def _make_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def test_user_defaults():
    async def scenario() -> None:
        engine, Session = _make_session_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with Session() as db:
            db.add(User(email="alice@example.com", hashed_password="hashed"))
            await db.commit()

        # Nouvelle session -> vrai aller-retour base (created_at posé côté DB).
        async with Session() as db:
            got = (
                await db.execute(select(User).where(User.email == "alice@example.com"))
            ).scalar_one()
            assert got.id is not None
            assert got.role == UserRole.user
            assert got.is_active is True
            assert got.created_at is not None

        await engine.dispose()

    asyncio.run(scenario())


def test_email_unique_constraint():
    async def scenario() -> None:
        engine, Session = _make_session_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with Session() as db:
            db.add(User(email="dup@example.com", hashed_password="x"))
            await db.commit()

        raised = False
        async with Session() as db:
            db.add(User(email="dup@example.com", hashed_password="y"))
            try:
                await db.commit()
            except IntegrityError:
                raised = True
        assert raised is True

        await engine.dispose()

    asyncio.run(scenario())
