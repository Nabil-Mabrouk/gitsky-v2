"""Routeur tutorials de bout en bout (Phase 3, incrément 3b).

Catalogue public + contrôle d'accès au contenu des leçons (public / premium).
Base SQLite dédiée (fichier temporaire) injectée par override de get_db.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401  (enregistre User)
import app.modules.tutorials.models  # noqa: E402,F401  (enregistre Tutorial/Lesson)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.tutorials import router as tutorials_router  # noqa: E402
from app.modules.tutorials.models import Lesson, Tutorial  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_tutorials_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
TestingSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSession() as db:
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        premium = User(
            email="p@x.com", hashed_password=hash_password("x"), role=UserRole.premium
        )
        db.add_all(
            [
                user,
                premium,
                Tutorial(
                    title="Intro",
                    slug="intro",
                    lang="fr",
                    access_role=UserRole.anonymous,
                    lessons=[Lesson(title="L1", order=1, content="public content")],
                ),
                Tutorial(
                    title="Advanced",
                    slug="advanced",
                    lang="fr",
                    access_role=UserRole.premium,
                    lessons=[Lesson(title="L1", order=1, content="premium content")],
                ),
            ]
        )
        await db.commit()
        await db.refresh(user)
        await db.refresh(premium)
        pub = (
            await db.execute(select(Lesson).join(Tutorial).where(Tutorial.slug == "intro"))
        ).scalar_one()
        adv = (
            await db.execute(
                select(Lesson).join(Tutorial).where(Tutorial.slug == "advanced")
            )
        ).scalar_one()
        SEED.update(
            user_id=user.id,
            premium_id=premium.id,
            pub_lesson=pub.id,
            adv_lesson=adv.id,
        )


asyncio.run(_seed())


async def _override_get_db():
    async with TestingSession() as session:
        yield session


app = FastAPI()
app.include_router(tutorials_router, prefix="/api/content")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_catalog_lists_tutorials_by_lang():
    r = client.get("/api/content/tutorials?lang=fr")
    assert r.status_code == 200
    assert {t["slug"] for t in r.json()} == {"intro", "advanced"}


def test_tutorial_detail_includes_lessons():
    r = client.get("/api/content/tutorials/intro")
    assert r.status_code == 200
    assert r.json()["lessons"][0]["title"] == "L1"


def test_public_lesson_readable_without_auth():
    r = client.get(f"/api/content/tutorials/intro/lessons/{SEED['pub_lesson']}")
    assert r.status_code == 200
    assert r.json()["content"] == "public content"


def test_premium_lesson_requires_auth():
    r = client.get(f"/api/content/tutorials/advanced/lessons/{SEED['adv_lesson']}")
    assert r.status_code == 401


def test_premium_lesson_forbidden_for_plain_user():
    r = client.get(
        f"/api/content/tutorials/advanced/lessons/{SEED['adv_lesson']}",
        headers=_auth(SEED["user_id"]),
    )
    assert r.status_code == 403


def test_premium_lesson_readable_by_premium_user():
    r = client.get(
        f"/api/content/tutorials/advanced/lessons/{SEED['adv_lesson']}",
        headers=_auth(SEED["premium_id"]),
    )
    assert r.status_code == 200
    assert r.json()["content"] == "premium content"


def test_unknown_tutorial_returns_404():
    assert client.get("/api/content/tutorials/nope").status_code == 404
