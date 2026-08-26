"""Monitoring de disponibilité de flotte (Phase 6, incr 6 — Chap 23).

Le fleet dashboard journalise `deployment_failed` quand un projet est muet sur
/health > 5 min, et `deployment_recovered` au retour — UNE seule fois par
transition. On teste la décision pure, la journalisation (sqlite), et le point
d'entrée /projects/health-sweep que le poller alimente.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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

import app.modules.fleet.models  # noqa: E402,F401
from app.core.config import Settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.modules.fleet import health_monitor as hm  # noqa: E402
from app.modules.fleet import router as fleet_router  # noqa: E402
from app.modules.fleet.models import FleetLifecycleEvent, Project  # noqa: E402

# `app.modules.fleet.__init__` does `from .router import router`, which rebinds
# the package's `router` attribute from the submodule to the APIRouter instance
# — so both `from app.modules.fleet import router` and even
# `import app.modules.fleet.router as x` (which resolves via that same
# attribute chain, not sys.modules) give the APIRouter, not the submodule.
# sys.modules is the only reliable way to reach the actual submodule, needed
# here to monkeypatch its `get_settings` reference.
fleet_router_module = sys.modules["app.modules.fleet.router"]

NOW = datetime(2026, 7, 17, 3, 0, 0, tzinfo=timezone.utc)


# --- Décision pure : muet > 5 min ------------------------------------------


def test_is_silent_thresholds():
    assert hm.is_silent(NOW, None) is True  # jamais vu -> muet
    assert hm.is_silent(NOW, NOW - timedelta(minutes=4)) is False  # < 5 min
    assert hm.is_silent(NOW, NOW - timedelta(minutes=6)) is True  # > 5 min
    # Exactement au seuil : 5 min pile n'est pas encore « plus de 5 min ».
    assert hm.is_silent(NOW, NOW - timedelta(minutes=5)) is False


# --- Journalisation des transitions (sqlite in-memory) ---------------------


def _fresh_db():
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def _seed_projects(factory, projects: list[tuple[str, str]]) -> None:
    async with factory() as db:
        for name, status in projects:
            db.add(Project(name=name, status=status))
        await db.commit()


async def _events(factory, name: str) -> list[str]:
    async with factory() as db:
        rows = (
            await db.execute(
                select(FleetLifecycleEvent.event_type)
                .where(FleetLifecycleEvent.project_name == name)
                .order_by(FleetLifecycleEvent.id)
            )
        ).scalars().all()
    return list(rows)


def test_silent_project_logs_deployment_failed_once():
    async def scenario():
        engine, factory = _fresh_db()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_projects(factory, [("pain-scraper", "active")])

        silent = {"pain-scraper": NOW - timedelta(minutes=10)}
        async with factory() as db:
            first = await hm.record_health_sweep(db, silent, NOW)
        # Deuxième passage, toujours muet : pas de second deployment_failed.
        async with factory() as db:
            second = await hm.record_health_sweep(db, silent, NOW + timedelta(minutes=1))

        events = await _events(factory, "pain-scraper")
        await engine.dispose()
        return first, second, events

    first, second, events = asyncio.run(scenario())
    assert first["failed"] == ["pain-scraper"]
    assert second["failed"] == []  # dédup : une seule alerte par panne
    assert events == ["deployment_failed"]


def test_recovery_logs_deployment_recovered():
    async def scenario():
        engine, factory = _fresh_db()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_projects(factory, [("pain-scraper", "active")])

        async with factory() as db:
            await hm.record_health_sweep(
                db, {"pain-scraper": NOW - timedelta(minutes=10)}, NOW
            )
        # Le projet répond de nouveau.
        async with factory() as db:
            recovered = await hm.record_health_sweep(
                db, {"pain-scraper": NOW + timedelta(minutes=2)}, NOW + timedelta(minutes=2)
            )
        events = await _events(factory, "pain-scraper")
        await engine.dispose()
        return recovered, events

    recovered, events = asyncio.run(scenario())
    assert recovered["recovered"] == ["pain-scraper"]
    assert events == ["deployment_failed", "deployment_recovered"]


def test_archived_projects_are_not_alarmed():
    async def scenario():
        engine, factory = _fresh_db()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_projects(factory, [("dead-idea", "archived")])
        # Muet, mais archived : une archive n'est pas une panne.
        async with factory() as db:
            changed = await hm.record_health_sweep(
                db, {"dead-idea": None}, NOW
            )
        events = await _events(factory, "dead-idea")
        await engine.dispose()
        return changed, events

    changed, events = asyncio.run(scenario())
    assert changed["failed"] == []
    assert events == []


def test_healthy_project_logs_nothing():
    async def scenario():
        engine, factory = _fresh_db()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _seed_projects(factory, [("healthy-app", "active")])
        async with factory() as db:
            changed = await hm.record_health_sweep(
                db, {"healthy-app": NOW - timedelta(minutes=1)}, NOW
            )
        events = await _events(factory, "healthy-app")
        await engine.dispose()
        return changed, events

    changed, events = asyncio.run(scenario())
    assert changed == {"failed": [], "recovered": []}
    assert events == []


# --- Endpoint /projects/health-sweep ---------------------------------------

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_hm_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

_engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_endpoint() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _factory() as db:
        db.add(Project(name="silent-one", status="active"))
        await db.commit()


asyncio.run(_seed_endpoint())


async def _override_get_db():
    async with _factory() as session:
        yield session


_app = FastAPI()
_app.include_router(fleet_router, prefix="/api/fleet")
_app.dependency_overrides[get_db] = _override_get_db
_client = TestClient(_app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(_engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


# health-sweep est appelé par fleet-health.sh, un script cron non-interactif
# (même raisonnement que register, Chap 19) — il ne peut pas fournir de JWT
# admin. Garde par token machine-à-machine partagé (X-Fleet-Token), pas
# require_admin. Token non-vide forcé ici pour exercer réellement la garde :
# vide = "ouvert" en dev (philosophie stub), ce qui ne testerait rien.
_FLEET_TOKEN = "test-fleet-token"  # noqa: S105


def _with_fleet_token(monkeypatch) -> None:
    fake_settings = Settings(fleet_register_token=_FLEET_TOKEN)
    monkeypatch.setattr(fleet_router_module, "get_settings", lambda: fake_settings)


def test_health_sweep_endpoint_requires_fleet_token(monkeypatch):
    _with_fleet_token(monkeypatch)
    assert _client.post(
        "/api/fleet/projects/health-sweep", json={"last_success": {}}
    ).status_code == 401
    assert _client.post(
        "/api/fleet/projects/health-sweep",
        json={"last_success": {}},
        headers={"X-Fleet-Token": "wrong-token"},
    ).status_code == 401


def test_health_sweep_endpoint_flags_silent_project(monkeypatch):
    _with_fleet_token(monkeypatch)
    old = (NOW - timedelta(minutes=30)).isoformat()
    r = _client.post(
        "/api/fleet/projects/health-sweep",
        json={"last_success": {"silent-one": old}, "now": NOW.isoformat()},
        headers={"X-Fleet-Token": _FLEET_TOKEN},
    )
    assert r.status_code == 200
    assert r.json()["failed"] == ["silent-one"]
