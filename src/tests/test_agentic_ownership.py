"""Propriété des exécutions agentic (durcissement — contrat d'ownership).

GET /executions/{id} renvoyait l'exécution de n'importe quel utilisateur à tout
porteur d'un access token (IDOR) : résultats de génération, paramètres d'entrée
et erreurs fuyaient entre comptes. Contrat : une exécution n'est visible que par
son propriétaire (et par un admin) ; pour les autres elle N'EXISTE PAS (404,
pas 403 — ne pas confirmer l'existence de l'id).

Toute ressource future porteuse d'un `user_id` doit suivre le même patron.
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

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_agentic_own_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        alice = User(email="alice@x.com", hashed_password=hash_password("x"))
        bob = User(email="bob@x.com", hashed_password=hash_password("x"))
        admin = User(
            email="admin@x.com", hashed_password=hash_password("x"), role=UserRole.admin
        )
        db.add_all([alice, bob, admin])
        await db.commit()
        for u in (alice, bob, admin):
            await db.refresh(u)
        SEED.update(alice=alice.id, bob=bob.id, admin=admin.id)


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


def _auth(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _execution_of_alice() -> int:
    r = client.post(
        "/api/agent-services/services/template_service/execute",
        json={"workflow_name": "example_workflow", "parameters": {"topic": "secret"}},
        headers=_auth(SEED["alice"]),
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_owner_reads_own_execution():
    exec_id = _execution_of_alice()
    r = client.get(f"/api/agent-services/executions/{exec_id}", headers=_auth(SEED["alice"]))
    assert r.status_code == 200
    assert r.json()["id"] == exec_id


def test_other_user_gets_404_not_the_data():
    exec_id = _execution_of_alice()
    r = client.get(f"/api/agent-services/executions/{exec_id}", headers=_auth(SEED["bob"]))
    # 404 et pas 403 : l'existence même de l'exécution ne doit pas fuiter.
    assert r.status_code == 404
    assert "secret" not in r.text


def test_admin_keeps_access_for_support():
    exec_id = _execution_of_alice()
    r = client.get(f"/api/agent-services/executions/{exec_id}", headers=_auth(SEED["admin"]))
    assert r.status_code == 200
