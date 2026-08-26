"""POST /api/fleet/webhooks/github/{name} (Chap 26, Phase D).

Même structure que test_fleet_register_token.py pour la garde M2M de
/register : signature configurée -> obligatoire et exacte (sinon 401) ;
secret absent -> ouvert en dev (philosophie stub), REFUS (503) en
production. Un événement `push` bien signé journalise un FleetLifecycleEvent
`deploy_triggered` ; un autre événement (ping) est un accusé de réception
silencieux, sans écriture en base.
"""

import asyncio
import atexit
import hashlib
import hmac
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

import app.core.models  # noqa: E402,F401
import app.modules.fleet.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.modules.fleet.models import FleetLifecycleEvent  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_fleet_webhook_{os.getpid()}.db"
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

SECRET = "s3cret-webhook"
PAYLOAD = b'{"ref": "refs/heads/main"}'


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


def _sign(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


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


async def _events_for(project: str) -> list[FleetLifecycleEvent]:
    async with factory() as session:
        result = await session.execute(
            select(FleetLifecycleEvent).where(
                FleetLifecycleEvent.project_name == project
            )
        )
        return list(result.scalars().all())


def test_webhook_accepts_valid_signature_and_logs_push():
    _, saved = _with_settings(fleet_github_webhook_secret=SECRET)
    try:
        r = client.post(
            "/api/fleet/webhooks/github/pain-scraper",
            content=PAYLOAD,
            headers={
                "X-Hub-Signature-256": _sign(PAYLOAD, SECRET),
                "X-GitHub-Event": "push",
                "content-type": "application/json",
            },
        )
        assert r.status_code == 204
        events = asyncio.run(_events_for("pain-scraper"))
        assert len(events) == 1
        assert events[0].event_type == "deploy_triggered"
        assert events[0].reason == "github_push"
    finally:
        _restore(saved)


def test_webhook_rejects_missing_or_wrong_signature():
    _, saved = _with_settings(fleet_github_webhook_secret=SECRET)
    try:
        r = client.post(
            "/api/fleet/webhooks/github/pain-scraper",
            content=PAYLOAD,
            headers={"X-GitHub-Event": "push"},
        )
        assert r.status_code == 401

        r = client.post(
            "/api/fleet/webhooks/github/pain-scraper",
            content=PAYLOAD,
            headers={
                "X-Hub-Signature-256": "sha256=deadbeef",
                "X-GitHub-Event": "push",
            },
        )
        assert r.status_code == 401
    finally:
        _restore(saved)


def test_webhook_fail_closed_in_production_without_secret():
    _, saved = _with_settings(fleet_github_webhook_secret="", environment="production")
    try:
        r = client.post(
            "/api/fleet/webhooks/github/pain-scraper",
            content=PAYLOAD,
            headers={"X-GitHub-Event": "push"},
        )
        assert r.status_code == 503
    finally:
        _restore(saved)


def test_webhook_stays_open_in_dev_without_secret():
    _, saved = _with_settings(fleet_github_webhook_secret="", environment="development")
    try:
        r = client.post(
            "/api/fleet/webhooks/github/dev-project",
            content=PAYLOAD,
            headers={"X-GitHub-Event": "push"},
        )
        assert r.status_code == 204
        events = asyncio.run(_events_for("dev-project"))
        assert len(events) == 1
    finally:
        _restore(saved)


def test_webhook_verifies_but_ignores_push_to_a_feature_branch():
    # Signature valide, événement push, mais pas la branche de déploiement :
    # reçu et vérifié, mais aucun deploy_triggered — le développeur n'a pas
    # fini, il n'a pas mergé.
    feature_payload = b'{"ref": "refs/heads/feature/wip-thing"}'
    _, saved = _with_settings(fleet_github_webhook_secret=SECRET)
    try:
        r = client.post(
            "/api/fleet/webhooks/github/feature-branch-project",
            content=feature_payload,
            headers={
                "X-Hub-Signature-256": _sign(feature_payload, SECRET),
                "X-GitHub-Event": "push",
            },
        )
        assert r.status_code == 204
        assert asyncio.run(_events_for("feature-branch-project")) == []
    finally:
        _restore(saved)


def test_webhook_deploys_on_the_configured_non_default_branch():
    prod_payload = b'{"ref": "refs/heads/production"}'
    _, saved = _with_settings(
        fleet_github_webhook_secret=SECRET, fleet_github_deploy_branch="production"
    )
    try:
        r = client.post(
            "/api/fleet/webhooks/github/prod-branch-project",
            content=prod_payload,
            headers={
                "X-Hub-Signature-256": _sign(prod_payload, SECRET),
                "X-GitHub-Event": "push",
            },
        )
        assert r.status_code == 204
        events = asyncio.run(_events_for("prod-branch-project"))
        assert len(events) == 1
        assert events[0].event_type == "deploy_triggered"
    finally:
        _restore(saved)


def test_webhook_ignores_non_push_events_without_writing_to_db():
    # Nom de projet dédié (pas "pain-scraper", déjà utilisé par un test push)
    # pour pouvoir affirmer zéro événement sans dépendre de l'ordre des tests.
    _, saved = _with_settings(fleet_github_webhook_secret=SECRET)
    try:
        r = client.post(
            "/api/fleet/webhooks/github/ping-only-project",
            content=PAYLOAD,
            headers={
                "X-Hub-Signature-256": _sign(PAYLOAD, SECRET),
                "X-GitHub-Event": "ping",
            },
        )
        assert r.status_code == 204
        assert asyncio.run(_events_for("ping-only-project")) == []
    finally:
        _restore(saved)
