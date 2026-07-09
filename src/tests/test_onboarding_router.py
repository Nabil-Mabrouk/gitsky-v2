"""Routeur onboarding de bout en bout (Phase 3, onboarding — API).

Flows + evaluate (public) et profile (authentifié, persistant + upsert).
Base SQLite fichier injectée par override de get_db.
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
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401  (User)
import app.modules.onboarding.models  # noqa: E402,F401  (UserProfile)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.onboarding import router as onboarding_router  # noqa: E402
from app.modules.onboarding.models import UserProfile  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_onboarding_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}
SOLO = {"role": "dev", "team_size": "solo", "goal": "speed"}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        SEED["user_id"] = user.id


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


app = FastAPI()
app.include_router(onboarding_router, prefix="/api/onboarding")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_access_token(SEED['user_id'])}"}


async def _profile_count_and_value() -> tuple[int, str | None]:
    async with factory() as db:
        count = (
            await db.execute(select(func.count()).select_from(UserProfile))
        ).scalar_one()
        row = (
            await db.execute(select(UserProfile).where(UserProfile.user_id == SEED["user_id"]))
        ).scalar_one_or_none()
        return count, (row.profile if row else None)


def test_get_flow_questions():
    r = client.get("/api/onboarding/flows/user_profiling")
    assert r.status_code == 200
    assert len(r.json()["questions"]) == 3


def test_get_flow_unknown_404():
    assert client.get("/api/onboarding/flows/nope").status_code == 404


def test_evaluate_matches_solo_builder():
    r = client.post(
        "/api/onboarding/evaluate",
        json={"flow_id": "user_profiling", "answers": SOLO},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "solo_builder"
    assert body["score"] == 80
    assert body["title"] == "Solo Builder"


def test_evaluate_falls_back_to_default():
    r = client.post(
        "/api/onboarding/evaluate",
        json={"flow_id": "user_profiling", "answers": {"role": "designer"}},
    )
    assert r.json()["profile"] == "explorer"


def test_profile_requires_auth():
    r = client.post(
        "/api/onboarding/profile",
        json={"flow_id": "user_profiling", "answers": SOLO},
    )
    assert r.status_code == 401


def test_profile_persists_then_upserts():
    r = client.post(
        "/api/onboarding/profile",
        json={"flow_id": "user_profiling", "answers": SOLO},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["profile"] == "solo_builder"

    count, value = asyncio.run(_profile_count_and_value())
    assert count == 1
    assert value == "solo_builder"

    # Deuxième évaluation : upsert (met à jour, ne duplique pas).
    r2 = client.post(
        "/api/onboarding/profile",
        json={"flow_id": "user_profiling", "answers": {"role": "designer"}},
        headers=_auth(),
    )
    assert r2.json()["profile"] == "explorer"

    count, value = asyncio.run(_profile_count_and_value())
    assert count == 1
    assert value == "explorer"
