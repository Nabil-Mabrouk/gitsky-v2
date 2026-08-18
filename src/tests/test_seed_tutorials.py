"""Seed de tutoriels depuis un dossier Markdown (Chap 11).

Vérifie l'extraction titre/contenu, la création initiale, et surtout
l'idempotence de l'upsert (rejouable après une édition du contenu source).
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

from app.core.database import Base  # noqa: E402
from app.core.models import UserRole  # noqa: E402
from app.modules.tutorials.models import Lesson, Tutorial  # noqa: E402
from scripts import seed_tutorials  # noqa: E402


def _fresh_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def _write(dir_: Path, name: str, text: str) -> None:
    (dir_ / name).write_text(text, encoding="utf-8")


def test_first_run_creates_tutorial_and_lessons(tmp_path):
    _write(tmp_path, "01.md", "# Premier chapitre\n\nContenu un.")
    _write(tmp_path, "02.md", "# Deuxième chapitre\n\nContenu deux.")

    async def scenario():
        engine, factory = _fresh_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        count = await seed_tutorials.seed(
            tmp_path, "guide", "Guide", "fr", UserRole.admin, session_factory=factory
        )

        async with factory() as db:
            tutorial = (
                await db.execute(select(Tutorial).where(Tutorial.slug == "guide"))
            ).scalar_one()
            lessons = (
                await db.execute(
                    select(Lesson)
                    .where(Lesson.tutorial_id == tutorial.id)
                    .order_by(Lesson.order)
                )
            ).scalars().all()

        await engine.dispose()
        return count, tutorial, lessons

    count, tutorial, lessons = asyncio.run(scenario())
    assert count == 2
    assert tutorial.title == "Guide"
    assert tutorial.access_role == UserRole.admin
    assert [lesson.title for lesson in lessons] == ["Premier chapitre", "Deuxième chapitre"]
    assert lessons[0].content == "Contenu un."
    assert lessons[0].order == 1
    assert lessons[1].order == 2


def test_rerun_after_edit_updates_in_place_no_duplicates(tmp_path):
    _write(tmp_path, "01.md", "# Titre v1\n\nContenu v1.")

    async def scenario():
        engine, factory = _fresh_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await seed_tutorials.seed(
            tmp_path, "guide", "Guide", "fr", UserRole.admin, session_factory=factory
        )

        # Le contenu source est édité (ex. correction du livre), puis reseedé.
        _write(tmp_path, "01.md", "# Titre v2\n\nContenu v2.")
        await seed_tutorials.seed(
            tmp_path, "guide", "Guide", "fr", UserRole.admin, session_factory=factory
        )

        async with factory() as db:
            tutorial_count = (
                await db.execute(select(func.count()).select_from(Tutorial))
            ).scalar_one()
            lesson_count = (
                await db.execute(select(func.count()).select_from(Lesson))
            ).scalar_one()
            lesson = (
                await db.execute(select(Lesson).where(Lesson.order == 1))
            ).scalar_one()

        await engine.dispose()
        return tutorial_count, lesson_count, lesson

    tutorial_count, lesson_count, lesson = asyncio.run(scenario())
    assert tutorial_count == 1
    assert lesson_count == 1
    assert lesson.title == "Titre v2"
    assert lesson.content == "Contenu v2."


def test_file_without_h1_falls_back_to_filename_stem(tmp_path):
    _write(tmp_path, "raw.md", "Just prose, no heading.")

    async def scenario():
        engine, factory = _fresh_factory()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await seed_tutorials.seed(
            tmp_path, "guide", "Guide", "fr", UserRole.admin, session_factory=factory
        )

        async with factory() as db:
            lesson = (await db.execute(select(Lesson))).scalar_one()

        await engine.dispose()
        return lesson

    lesson = asyncio.run(scenario())
    assert lesson.title == "raw"
    assert lesson.content == "Just prose, no heading."
