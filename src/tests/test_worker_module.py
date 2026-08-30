"""Module worker de bout en bout (round worker).

`WorkerRun` (défaut de statut), `recover_interrupted_runs` (rattrapage au
boot du process worker) et l'endpoint `/status` (auth admin, tri/limite).
Base SQLite dédiée (fichier temporaire) injectée par override de get_db —
même patron que `test_tutorials_router.py`.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401  (enregistre User)
import app.modules.worker.models  # noqa: E402,F401  (enregistre WorkerRun)
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.worker import router as worker_router  # noqa: E402
from app.modules.worker.models import WorkerRun  # noqa: E402
from app.modules.worker.recovery import recover_interrupted_runs  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_worker_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
TestingSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSession() as db:
        admin = User(
            email="admin@x.com", hashed_password=hash_password("x"), role=UserRole.admin
        )
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add_all([admin, user])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        SEED.update(admin_id=admin.id, user_id=user.id)


asyncio.run(_seed())


async def _override_get_db():
    async with TestingSession() as session:
        yield session


app = FastAPI()
app.include_router(worker_router, prefix="/api/worker")
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


def _run_session_factory():
    return TestingSession


def test_worker_run_defaults_to_running_status():
    # Column(default=...) ne s'applique qu'à l'insertion (flush/commit), pas
    # à la construction Python — vérifié via un aller-retour DB réel.
    async def _insert_bare() -> int:
        async with TestingSession() as db:
            run = WorkerRun()
            db.add(run)
            await db.commit()
            await db.refresh(run)
            return run.id

    run_id = asyncio.run(_insert_bare())

    async def _check() -> WorkerRun:
        async with TestingSession() as db:
            run = await db.get(WorkerRun, run_id)
            assert run is not None
            return run

    run = asyncio.run(_check())
    assert run.status == "running"
    assert run.finished_at is None
    assert run.error is None


def test_status_requires_auth():
    assert client.get("/api/worker/status").status_code == 401


def test_status_forbidden_for_plain_user():
    r = client.get("/api/worker/status", headers=_auth(SEED["user_id"]))
    assert r.status_code == 403


def test_status_orders_most_recent_first():
    async def _seed_runs() -> None:
        async with TestingSession() as db:
            db.add_all(
                [
                    WorkerRun(
                        status="success",
                        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                        finished_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
                    ),
                    WorkerRun(
                        status="failed",
                        started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                        error="boom",
                    ),
                ]
            )
            await db.commit()

    asyncio.run(_seed_runs())

    r = client.get("/api/worker/status", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    body = r.json()
    # D'autres tests de ce fichier partagent la même base SQLite (état non
    # isolé par test) — on repère nos deux lignes par leur `error` distinctif
    # plutôt que de supposer une longueur/position absolue de la liste.
    failed_idx = next(i for i, run in enumerate(body) if run["error"] == "boom")
    success_idx = next(
        i for i, run in enumerate(body) if run["finished_at"] == "2026-01-01T00:05:00"
    )
    # started_at DESC : notre ligne "failed" (2026-01-02) est plus récente
    # que notre ligne "success" (2026-01-01), donc classée avant.
    assert failed_idx < success_idx
    assert body[failed_idx]["status"] == "failed"
    assert body[success_idx]["status"] == "success"


def test_recover_interrupted_runs_marks_running_as_interrupted():
    async def _seed_orphan() -> int:
        async with TestingSession() as db:
            run = WorkerRun(status="running")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            return run.id

    orphan_id = asyncio.run(_seed_orphan())

    recovered = asyncio.run(recover_interrupted_runs(_run_session_factory()))
    assert recovered >= 1

    async def _check() -> str:
        async with TestingSession() as db:
            run = await db.get(WorkerRun, orphan_id)
            assert run is not None
            return run.status

    assert asyncio.run(_check()) == "interrupted"


def test_recover_interrupted_runs_leaves_terminal_statuses_untouched():
    async def _seed_success() -> int:
        async with TestingSession() as db:
            run = WorkerRun(status="success")
            db.add(run)
            await db.commit()
            await db.refresh(run)
            return run.id

    success_id = asyncio.run(_seed_success())
    asyncio.run(recover_interrupted_runs(_run_session_factory()))

    async def _check() -> str:
        async with TestingSession() as db:
            run = await db.get(WorkerRun, success_id)
            assert run is not None
            return run.status

    assert asyncio.run(_check()) == "success"
