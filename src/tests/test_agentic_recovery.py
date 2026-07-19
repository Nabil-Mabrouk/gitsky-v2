"""Récupération des jobs agentic orphelins (durcissement).

Les workflows longs vivent dans des `asyncio.Task` en mémoire : un redémarrage
(deploy, crash) les emportait — exécutions bloquées `pending`/`running` pour
toujours, crédits débités jamais remboursés. Contrat :

1. le coût débité est PERSISTÉ sur l'exécution (`cost_credits`) — condition de
   tout remboursement après coup ;
2. au démarrage, `recover_orphan_executions` marque `failed` les exécutions
   `pending`/`running` et rembourse leur coût ;
3. `_run_job` rembourse aussi quand le workflow échoue en vol.
"""

import asyncio
import atexit
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "generator" / "template"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import importlib  # noqa: E402

import app.core.models  # noqa: E402,F401
import app.modules.agentic.models  # noqa: E402,F401
from app.core.auth.security import hash_password  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.models import User  # noqa: E402
from app.modules.agentic import credits  # noqa: E402
from app.modules.agentic.models import CreditAccount, ServiceExecution  # noqa: E402
from app.modules.agentic.recovery import recover_orphan_executions  # noqa: E402

# Le package agentic exporte un attribut `router` (l'APIRouter) qui masque le
# sous-module du même nom : import_module va chercher le MODULE, lui.
agentic_router_module = importlib.import_module("app.modules.agentic.router")

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_agentic_rec_{os.getpid()}.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}")
factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SEED: dict[str, int] = {}


async def _seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        user = User(email="u@x.com", hashed_password=hash_password("x"))
        db.add(user)
        await db.commit()
        await db.refresh(user)
        SEED["user_id"] = user.id
        db.add(CreditAccount(user_id=user.id, balance=5))
        await db.commit()


asyncio.run(_seed())


@atexit.register
def _cleanup() -> None:
    asyncio.run(engine.dispose())
    try:
        _DB_FILE.unlink()
    except OSError:
        pass


async def _balance() -> int:
    async with factory() as db:
        account = (
            await db.execute(
                select(CreditAccount).where(CreditAccount.user_id == SEED["user_id"])
            )
        ).scalar_one()
        return account.balance


async def _add_execution(status: str, cost: int) -> int:
    async with factory() as db:
        ex = ServiceExecution(
            user_id=SEED["user_id"],
            service_slug="svc",
            workflow_name="wf",
            status=status,
            input_params={},
            cost_credits=cost,
        )
        db.add(ex)
        await db.commit()
        await db.refresh(ex)
        return ex.id


async def _status_of(execution_id: int) -> str:
    async with factory() as db:
        return (await db.get(ServiceExecution, execution_id)).status


def test_startup_recovery_fails_orphans_and_refunds():
    async def scenario():
        running_id = await _add_execution("running", cost=4)
        pending_id = await _add_execution("pending", cost=0)
        completed_id = await _add_execution("completed", cost=2)

        recovered = await recover_orphan_executions(factory)

        return (
            recovered,
            await _status_of(running_id),
            await _status_of(pending_id),
            await _status_of(completed_id),
            await _balance(),
        )

    recovered, running, pending, completed, balance = asyncio.run(scenario())
    assert recovered == 2  # les deux orphelines, pas la terminée
    assert running == "failed"
    assert pending == "failed"
    assert completed == "completed"  # une exécution terminée n'est jamais touchée
    assert balance == 5 + 4  # seul le coût réellement débité est remboursé


def test_run_job_refunds_cost_on_workflow_failure(monkeypatch):
    # Service dont l'unique step référence un tool inconnu -> le moteur échoue.
    broken = {
        "steps": {"boom": {"type": "tool", "tool": "inexistant"}},
        "workflows": {"wf": ["boom"]},
    }
    monkeypatch.setattr(agentic_router_module, "get_service", lambda slug: broken)
    monkeypatch.setattr(agentic_router_module, "SessionLocal", factory)

    async def scenario():
        before = await _balance()
        execution_id = await _add_execution("pending", cost=3)
        async with factory() as db:
            await credits.debit(db, SEED["user_id"], 3)

        await agentic_router_module._run_job(
            execution_id, "svc", "wf", {}, SEED["user_id"], 3
        )
        return before, await _status_of(execution_id), await _balance()

    before, status, after = asyncio.run(scenario())
    assert status == "failed"
    assert after == before  # débit puis remboursement : solde inchangé
