"""Registre fleet de bout en bout (Phase 4, fleet — registre).

Enregistrement d'un projet (upsert, appelé par le générateur) + grille projets
réservée à l'opérateur. Base SQLite fichier injectée par override de get_db.
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

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
from app.core import mailer  # noqa: E402
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.fleet import landing_collector_client  # noqa: E402
from app.modules.fleet import router as fleet_router  # noqa: E402
from app.modules.fleet.models import FleetLifecycleEvent, Project  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


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


async def _project_count() -> int:
    async with factory() as db:
        return (await db.execute(select(func.count()).select_from(Project))).scalar_one()


def test_register_then_upsert():
    r = client.post(
        "/api/fleet/projects/register",
        json={"name": "pain-scraper", "domain": "pain-scraper.mystudio.com"},
    )
    assert r.status_code == 200
    assert r.json()["domain"] == "pain-scraper.mystudio.com"

    # Ré-enregistrement du même projet -> upsert (met à jour, pas de doublon).
    r2 = client.post(
        "/api/fleet/projects/register",
        json={"name": "pain-scraper", "domain": "pain-scraper.com"},
    )
    assert r2.status_code == 200
    assert r2.json()["domain"] == "pain-scraper.com"
    assert asyncio.run(_project_count()) == 1


def test_projects_grid_requires_admin():
    assert client.get("/api/fleet/projects").status_code == 401
    assert (
        client.get("/api/fleet/projects", headers=_auth(SEED["user_id"])).status_code
        == 403
    )
    r = client.get("/api/fleet/projects", headers=_auth(SEED["admin_id"]))
    assert r.status_code == 200
    assert any(p["name"] == "pain-scraper" for p in r.json())


def test_publish_promotion_flow():
    client.post(
        "/api/fleet/projects/register",
        json={"name": "launch-me", "domain": "launch-me.mystudio.com"},
    )
    assert client.post("/api/fleet/projects/launch-me/promote", json={}).status_code == 401

    # draft -> preview (toujours autorisé).
    r1 = client.post(
        "/api/fleet/projects/launch-me/promote",
        json={"guardrails_pass": True},
        headers=_auth(SEED["admin_id"]),
    )
    assert r1.json()["allowed"] is True
    assert r1.json()["publish_status"] == "preview"

    # preview -> live (sous-domaine de la flotte + guardrails OK => auto).
    r2 = client.post(
        "/api/fleet/projects/launch-me/promote",
        json={"guardrails_pass": True},
        headers=_auth(SEED["admin_id"]),
    )
    assert r2.json()["publish_status"] == "live"


def test_archive_requires_admin():
    client.post(
        "/api/fleet/projects/register",
        json={"name": "to-archive", "domain": "to-archive.mystudio.com"},
    )
    assert client.post("/api/fleet/projects/to-archive/archive").status_code == 401
    assert (
        client.post(
            "/api/fleet/projects/to-archive/archive", headers=_auth(SEED["user_id"])
        ).status_code
        == 403
    )


def test_archive_sets_status_and_journals_event_once():
    client.post(
        "/api/fleet/projects/register",
        json={"name": "archive-me", "domain": "archive-me.mystudio.com"},
    )
    r = client.post(
        "/api/fleet/projects/archive-me/archive", headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    async def _events() -> int:
        async with factory() as db:
            result = await db.execute(
                select(func.count())
                .select_from(FleetLifecycleEvent)
                .where(
                    FleetLifecycleEvent.project_name == "archive-me",
                    FleetLifecycleEvent.event_type == "archived",
                )
            )
            return result.scalar_one()

    assert asyncio.run(_events()) == 1

    # Idempotent : réarchiver ne journalise pas un second événement.
    r2 = client.post(
        "/api/fleet/projects/archive-me/archive", headers=_auth(SEED["admin_id"])
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "archived"
    assert asyncio.run(_events()) == 1


def test_archive_unknown_project_is_404():
    r = client.post(
        "/api/fleet/projects/does-not-exist/archive", headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 404


def test_project_leads_requires_admin_and_proxies_landing_collector(monkeypatch):
    assert client.get("/api/fleet/projects/pain-scraper/leads").status_code == 401
    assert (
        client.get(
            "/api/fleet/projects/pain-scraper/leads", headers=_auth(SEED["user_id"])
        ).status_code
        == 403
    )

    async def fake_fetch_leads(project: str) -> list[dict]:
        assert project == "pain-scraper"
        return [
            {
                "id": 1,
                "project": "pain-scraper",
                "email": "a@b.com",
                "source": "reddit",
                "utm_campaign": "",
                "created_at": "2026-08-01T00:00:00Z",
                "verified": False,
            }
        ]

    monkeypatch.setattr(landing_collector_client, "fetch_leads", fake_fetch_leads)

    r = client.get(
        "/api/fleet/projects/pain-scraper/leads", headers=_auth(SEED["admin_id"])
    )
    assert r.status_code == 200
    assert r.json() == [
        {
            "id": 1,
            "project": "pain-scraper",
            "email": "a@b.com",
            "source": "reddit",
            "utm_campaign": "",
            "created_at": "2026-08-01T00:00:00Z",
            "verified": False,
        }
    ]


def test_maintenance_report_persists_run_and_is_listable():
    r = client.post(
        "/api/fleet/maintenance/report",
        json={"job": "disk-check", "status": "success", "summary": "Disque / : 42%"},
    )
    assert r.status_code == 204

    runs = client.get(
        "/api/fleet/maintenance/runs", headers=_auth(SEED["admin_id"])
    ).json()
    assert any(
        r["job"] == "disk-check" and r["status"] == "success" and r["summary"] == "Disque / : 42%"
        for r in runs
    )


def test_maintenance_report_failure_sends_alert_but_never_blocks(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "ops@example.com")
    sent: dict = {}

    def fake_send_email(to: str, subject: str, body: str) -> None:
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    r = client.post(
        "/api/fleet/maintenance/report",
        json={
            "job": "restore-test",
            "status": "failure",
            "summary": "Aucune table après restauration.",
            "project": "pain_scraper",
        },
    )
    assert r.status_code == 204
    assert sent["to"] == "ops@example.com"
    assert "restore-test" in sent["subject"]
    assert sent["body"] == "Aucune table après restauration."


def test_maintenance_report_success_does_not_send_alert(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "ops@example.com")
    calls = []
    monkeypatch.setattr(mailer, "send_email", lambda **kw: calls.append(kw))

    r = client.post(
        "/api/fleet/maintenance/report",
        json={"job": "backup-fleet", "status": "success", "summary": "2 projets sauvegardés."},
    )
    assert r.status_code == 204
    assert calls == []


def test_maintenance_report_alert_failure_does_not_break_the_endpoint(monkeypatch):
    # L'alerte est un enrichissement : un mailer qui lève ne doit jamais faire
    # échouer le reporting lui-même (la ligne est déjà persistée avant l'email).
    monkeypatch.setenv("SMTP_FROM", "ops@example.com")

    def broken_send_email(**kw):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr(mailer, "send_email", broken_send_email)

    r = client.post(
        "/api/fleet/maintenance/report",
        json={"job": "backup-fleet", "status": "failure", "summary": "1 échec."},
    )
    assert r.status_code == 204


def test_maintenance_runs_sorted_most_recent_first_and_requires_admin():
    assert client.get("/api/fleet/maintenance/runs").status_code == 401
    assert (
        client.get(
            "/api/fleet/maintenance/runs", headers=_auth(SEED["user_id"])
        ).status_code
        == 403
    )

    client.post(
        "/api/fleet/maintenance/report",
        json={"job": "order-check-a", "status": "success"},
    )
    client.post(
        "/api/fleet/maintenance/report",
        json={"job": "order-check-b", "status": "success"},
    )

    runs = client.get(
        "/api/fleet/maintenance/runs", headers=_auth(SEED["admin_id"])
    ).json()
    jobs = [r["job"] for r in runs if r["job"].startswith("order-check")]
    assert jobs == ["order-check-b", "order-check-a"]
