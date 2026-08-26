"""GET /api/fleet/activity et le champ `health` de GET /api/fleet/projects
(Chap 28, refonte visuelle).

L'onglet Activité fusionne fleet_lifecycle_events et fleet_maintenance_runs
sans dupliquer aucune donnée (Chap 19 §« pas de duplication ») ; la grille
attache un `health` calculé par projet en une seule requête (pas de N+1,
health_monitor.bulk_health_status, déjà testé isolément dans
test_fleet_health_monitor.py). Ce fichier vérifie l'assemblage HTTP.
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
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.fleet import health_monitor as hm  # noqa: E402
from app.modules.fleet import router as fleet_router  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_activity_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}
NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        admin = User(email="a@x.com", hashed_password=hash_password("x"), role=UserRole.admin)
        user = User(email="u@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add_all([admin, user])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(user)
        SEED.update(admin_id=admin.id, user_id=user.id)


asyncio.run(_seed())


async def _override_get_db():
    async with factory() as session:
        yield session


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


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_activity_requires_admin():
    assert client.get("/api/fleet/activity").status_code == 401
    assert (
        client.get("/api/fleet/activity", headers=_auth(SEED["user_id"])).status_code
        == 403
    )


def test_activity_merges_lifecycle_and_maintenance_entries():
    client.post(
        "/api/fleet/projects/register",
        json={"name": "activity-project", "domain": "activity-project.mystudio.com"},
    )
    client.post(
        "/api/fleet/projects/activity-project/archive", headers=_auth(SEED["admin_id"])
    )
    client.post(
        "/api/fleet/maintenance/report",
        json={"job": "backup-fleet", "status": "success", "summary": "1 projet sauvegardé."},
    )

    r = client.get("/api/fleet/activity", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    entries = r.json()

    lifecycle_labels = {e["label"] for e in entries if e["kind"] == "lifecycle"}
    assert "born" in lifecycle_labels
    assert "archived" in lifecycle_labels

    maintenance = [e for e in entries if e["kind"] == "maintenance" and e["label"] == "backup-fleet"]
    assert len(maintenance) == 1
    assert maintenance[0]["status"] == "success"
    assert maintenance[0]["detail"] == "1 projet sauvegardé."
    assert maintenance[0]["project"] is None


def test_activity_respects_limit_and_caps_it():
    for i in range(5):
        client.post(
            "/api/fleet/projects/register",
            json={"name": f"limit-project-{i}", "domain": ""},
        )

    r = client.get("/api/fleet/activity?limit=2", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    assert len(r.json()) <= 2

    # limit=0 est plancher à 1, pas 0 (jamais une liste vide implicite par abus de paramètre).
    r0 = client.get("/api/fleet/activity?limit=0", headers=_auth(SEED["admin_id"]))
    assert len(r0.json()) == 1


def test_projects_grid_reports_health_per_project():
    client.post(
        "/api/fleet/projects/register",
        json={"name": "health-failing", "domain": ""},
    )

    async def _fail_it():
        async with factory() as db:
            await hm.record_health_sweep(
                db, {"health-failing": NOW - timedelta(minutes=30)}, NOW
            )

    asyncio.run(_fail_it())

    # Enregistré APRÈS le balayage : record_health_sweep interroge tous les
    # projets non-archivés, donc un projet déjà présent au moment du balayage
    # et absent de `last_success` serait lui aussi jugé muet (silencieux =
    # jamais vu) et recevrait un deployment_failed — ce n'est pas ce que ce
    # test veut vérifier. "unknown" ne peut décrire qu'un projet n'ayant
    # encore traversé AUCUN balayage.
    client.post(
        "/api/fleet/projects/register",
        json={"name": "health-unknown", "domain": ""},
    )

    grid = client.get("/api/fleet/projects", headers=_auth(SEED["admin_id"])).json()
    by_name = {p["name"]: p for p in grid}
    assert by_name["health-failing"]["health"] == "failing"
    assert by_name["health-unknown"]["health"] == "unknown"
