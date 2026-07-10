"""Modèles du module `tutorials` (Phase 3, incrément 3a).

Vérifie la relation One-to-Many ordonnée Tutorial->Lesson et la cascade ORM
(supprimer un tutorial supprime ses leçons). Moteur in-memory dédié (StaticPool).
En async, les relations se chargent via selectinload (pas de lazy load).
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.modules.tutorials.models import Lesson, Tutorial  # noqa: E402


def _session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_tutorial_lessons_ordered_and_cascade():
    async def scenario() -> None:
        engine, Session = _session_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with Session() as db:
            db.add(
                Tutorial(
                    title="Intro FastAPI",
                    slug="intro-fastapi",
                    lessons=[
                        Lesson(title="Deuxième", order=2, content="b"),
                        Lesson(title="Première", order=1, content="a"),
                    ],
                )
            )
            await db.commit()

        # Relation ordonnée par Lesson.order (chargée via selectinload).
        async with Session() as db:
            tuto = (
                await db.execute(
                    select(Tutorial)
                    .where(Tutorial.slug == "intro-fastapi")
                    .options(selectinload(Tutorial.lessons))
                )
            ).scalar_one()
            assert [lesson.title for lesson in tuto.lessons] == ["Première", "Deuxième"]

            # Cascade ORM : supprimer le tutorial supprime ses leçons.
            await db.delete(tuto)
            await db.commit()

        async with Session() as db:
            assert (await db.execute(select(func.count()).select_from(Lesson))).scalar_one() == 0
            assert (
                await db.execute(select(func.count()).select_from(Tutorial))
            ).scalar_one() == 0

        await engine.dispose()

    asyncio.run(scenario())
