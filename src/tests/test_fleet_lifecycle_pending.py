"""GET /api/fleet/lifecycle/pending (Chap 20/23, round sécurisation).

Même patron exact que test_fleet_deploys_pending.py : le dashboard n'a aucun
accès Docker (Chap 26 §choix d'architecture) — il journalise seulement
l'intention (stop/start/maintenance/maintenance_cleared), c'est cet endpoint
que lifecycle-fleet.sh interroge pour savoir quoi exécuter réellement.
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
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.modules.fleet.models import FleetLifecycleEvent  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_lifecycle_pending_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())


async def _override_get_db():
    async with factory() as session:
        yield session


from app.modules.fleet import router as fleet_router  # noqa: E402

app = FastAPI()
app.include_router(fleet_router, prefix="/api/fleet")
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _with_settings(**overrides):
    settings = get_settings()
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings, saved


def _restore(saved: dict) -> None:
    settings = get_settings()
    for k, v in saved.items():
        setattr(settings, k, v)


async def _seed(*, project: str, event_type: str) -> int:
    async with factory() as session:
        event = FleetLifecycleEvent(project_name=project, event_type=event_type)
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event.id


def test_pending_requires_valid_token():
    _, saved = _with_settings(fleet_register_token="s3cret-lifecycle")
    try:
        assert client.get("/api/fleet/lifecycle/pending").status_code == 401
        r = client.get(
            "/api/fleet/lifecycle/pending", headers={"X-Fleet-Token": "mauvais"}
        )
        assert r.status_code == 401
    finally:
        _restore(saved)


def test_pending_lists_all_four_action_types_with_action_column():
    _, saved = _with_settings(fleet_register_token="s3cret-lifecycle")
    try:
        id_stop = asyncio.run(_seed(project="alpha", event_type="stop_requested"))
        id_start = asyncio.run(_seed(project="beta", event_type="start_requested"))
        id_maint = asyncio.run(_seed(project="gamma", event_type="maintenance_requested"))
        id_clear = asyncio.run(_seed(project="delta", event_type="maintenance_cleared"))

        r = client.get(
            "/api/fleet/lifecycle/pending",
            headers={"X-Fleet-Token": "s3cret-lifecycle"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        lines = [line for line in r.text.splitlines() if line]
        assert f"{id_stop}\talpha\tstop" in lines
        assert f"{id_start}\tbeta\tstart" in lines
        assert f"{id_maint}\tgamma\tmaintenance" in lines
        assert f"{id_clear}\tdelta\tmaintenance-clear" in lines
    finally:
        _restore(saved)


def test_pending_respects_since_id_cursor():
    _, saved = _with_settings(fleet_register_token="s3cret-lifecycle")
    try:
        id1 = asyncio.run(_seed(project="epsilon", event_type="stop_requested"))
        id2 = asyncio.run(_seed(project="zeta", event_type="start_requested"))

        r = client.get(
            f"/api/fleet/lifecycle/pending?since_id={id1}",
            headers={"X-Fleet-Token": "s3cret-lifecycle"},
        )
        lines = [line for line in r.text.splitlines() if line]
        assert not any(line.startswith(f"{id1}\t") for line in lines)
        assert f"{id2}\tzeta\tstart" in lines
    finally:
        _restore(saved)


def test_pending_ignores_deploy_triggered_and_archived_events():
    # `archived` lui-même ne doit jamais apparaître ici — seul le
    # stop_requested qu'il journalise EN PLUS (archive_project) doit y
    # figurer, pas l'événement `archived` lui-même.
    _, saved = _with_settings(fleet_register_token="s3cret-lifecycle")
    try:
        asyncio.run(_seed(project="theta-only", event_type="deploy_triggered"))
        asyncio.run(_seed(project="theta-only", event_type="archived"))

        r = client.get(
            "/api/fleet/lifecycle/pending",
            headers={"X-Fleet-Token": "s3cret-lifecycle"},
        )
        assert "theta-only" not in r.text
    finally:
        _restore(saved)


def test_pending_empty_response_when_nothing_pending():
    _, saved = _with_settings(fleet_register_token="s3cret-lifecycle-empty")
    try:
        r = client.get(
            "/api/fleet/lifecycle/pending?since_id=999999999",
            headers={"X-Fleet-Token": "s3cret-lifecycle-empty"},
        )
        assert r.status_code == 200
        assert r.text == ""
    finally:
        _restore(saved)
