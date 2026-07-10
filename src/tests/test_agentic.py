"""Module agentic (Phase 3) — registre YAML, client LLM stub, API d'exécution.

Registre + llm (purs) + routeur (catalogue public, exécution authentifiée tracée).
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
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.core.models  # noqa: E402,F401
import app.modules.agentic.models  # noqa: E402,F401
from app.core.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.agentic import router as agentic_router  # noqa: E402
from app.modules.agentic.llm_client import call_llm  # noqa: E402
from app.modules.agentic.registry import get_service, load_services  # noqa: E402


# --- Registre + LLM (purs) ------------------------------------------------

def test_registry_loads_services():
    services = load_services()
    assert "template_service" in services
    assert get_service("template_service")["name"] == "Service Exemple"
    assert get_service("inconnu") is None


def test_llm_client_is_stub():
    out = call_llm("claude-sonnet-4-6", [{"role": "user", "content": "salut"}])
    assert "stub" in out
    assert "salut" in out


# --- Intégration routeur --------------------------------------------------

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_agentic_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


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
app.include_router(agentic_router, prefix="/api/agent-services")
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


def test_catalog_public():
    r = client.get("/api/agent-services/services")
    assert r.status_code == 200
    assert any(s["slug"] == "template_service" for s in r.json())


def test_service_detail_unknown_404():
    assert client.get("/api/agent-services/services/nope").status_code == 404


def test_execute_requires_auth():
    r = client.post(
        "/api/agent-services/services/template_service/execute",
        json={"workflow_name": "example_workflow", "parameters": {}},
    )
    assert r.status_code == 401


def test_execute_traces_and_returns_result():
    r = client.post(
        "/api/agent-services/services/template_service/execute",
        json={"workflow_name": "example_workflow", "parameters": {"topic": "ia"}},
        headers=_auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert "stub" in body["result"]["output"]

    # L'exécution est tracée et récupérable.
    got = client.get(f"/api/agent-services/executions/{body['id']}", headers=_auth())
    assert got.status_code == 200
    assert got.json()["service_slug"] == "template_service"
