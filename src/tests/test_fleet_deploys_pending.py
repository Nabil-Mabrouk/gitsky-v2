"""GET /api/fleet/deploys/pending (Chap 26, Phase D).

Le webhook GitHub (Chap 26) journalise `deploy_triggered` mais n'exécute rien
lui-même — c'est cet endpoint que deploy-on-push.sh interroge pour savoir quoi
redéployer, avec un accès Docker que le conteneur dashboard n'a jamais.

Même garde M2M que /register, /health-sweep, /maintenance/report
(verify_fleet_service_token) : ce n'est pas une route opérateur.
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

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_pending_{os.getpid()}.db"
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


async def _seed(*, project: str, event_type: str = "deploy_triggered") -> int:
    async with factory() as session:
        event = FleetLifecycleEvent(
            project_name=project, event_type=event_type, reason="github_push"
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event.id


def test_pending_requires_valid_token():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        assert (
            client.get("/api/fleet/deploys/pending").status_code == 401
        )
        r = client.get(
            "/api/fleet/deploys/pending",
            headers={"X-Fleet-Token": "mauvais"},
        )
        assert r.status_code == 401
    finally:
        _restore(saved)


def test_pending_fail_closed_in_production_without_token():
    _, saved = _with_settings(fleet_register_token="", environment="production")
    try:
        assert client.get("/api/fleet/deploys/pending").status_code == 503
    finally:
        _restore(saved)


def test_pending_lists_deploy_triggered_events_as_tab_separated_lines():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        id1 = asyncio.run(_seed(project="alpha"))
        id2 = asyncio.run(_seed(project="beta"))

        r = client.get(
            "/api/fleet/deploys/pending",
            headers={"X-Fleet-Token": "s3cret-fleet"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        lines = [line for line in r.text.splitlines() if line]
        assert f"{id1}\talpha" in lines
        assert f"{id2}\tbeta" in lines
    finally:
        _restore(saved)


def test_pending_respects_since_id_cursor():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        id1 = asyncio.run(_seed(project="gamma"))
        id2 = asyncio.run(_seed(project="delta"))

        r = client.get(
            f"/api/fleet/deploys/pending?since_id={id1}",
            headers={"X-Fleet-Token": "s3cret-fleet"},
        )
        assert r.status_code == 200
        lines = [line for line in r.text.splitlines() if line]
        assert f"{id1}\tgamma" not in lines
        assert f"{id2}\tdelta" in lines
    finally:
        _restore(saved)


def test_pending_ignores_non_deploy_triggered_events():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet")
    try:
        asyncio.run(_seed(project="epsilon", event_type="born"))

        r = client.get(
            "/api/fleet/deploys/pending",
            headers={"X-Fleet-Token": "s3cret-fleet"},
        )
        assert r.status_code == 200
        assert "epsilon" not in r.text
    finally:
        _restore(saved)


def test_pending_empty_response_when_nothing_pending():
    _, saved = _with_settings(fleet_register_token="s3cret-fleet-empty")
    try:
        r = client.get(
            "/api/fleet/deploys/pending?since_id=999999999",
            headers={"X-Fleet-Token": "s3cret-fleet-empty"},
        )
        assert r.status_code == 200
        assert r.text == ""
    finally:
        _restore(saved)
