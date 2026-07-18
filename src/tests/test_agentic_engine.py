"""Moteur agentic (Chap 15) : orchestration multi-étapes, tool, crédits, stub Suno.

Teste `engine.execute_workflow` directement (async) sur une base SQLite dédiée,
avec un service synthétique (une étape agent + une étape tool). Le chemin ROUTER
async (submit-and-return + polling) est vérifié de bout en bout dans la démo
Docker (event loop uvicorn réel) — TestClient + asyncio.create_task est trop
fragile pour un test unitaire fiable.
"""

import asyncio
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

import app.core.models  # noqa: E402,F401
import app.modules.agentic.models  # noqa: E402,F401
from app.core.auth.security import hash_password  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.models import User, UserRole  # noqa: E402
from app.modules.agentic import credits, engine  # noqa: E402
from app.modules.agentic.models import ExecutionStep, ServiceExecution  # noqa: E402
from app.modules.agentic.tools.suno import suno_generate  # noqa: E402

SERVICE = {
    "steps": {
        "write": {"type": "agent", "model": "claude-sonnet-5", "system_prompt": "écris"},
        "render": {"type": "tool", "tool": "suno_generate"},
        "boom": {"type": "tool", "tool": "does_not_exist"},
    },
    "workflows": {"song": ["write", "render"], "broken": ["write", "boom"]},
    "async_workflows": ["song"],
    "cost_credits": 3,
}


async def _fresh_db():
    dbpath = Path(tempfile.mktemp(suffix=".db"))
    eng = create_async_engine(f"sqlite+aiosqlite:///{dbpath.as_posix()}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(email="e@x.com", hashed_password=hash_password("x"), role=UserRole.user)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        uid = user.id
    return eng, factory, dbpath, uid


def test_suno_stub_returns_audio_url():
    out = asyncio.run(suno_generate({"parameters": {"voice": "x"}, "lyrics": "la"}, {}))
    assert out["stub"] is True
    assert out["status"] == "done"
    assert out["audio_url"].endswith(".mp3")


def test_engine_runs_multi_step_and_records_steps():
    async def scenario():
        eng, factory, dbpath, uid = await _fresh_db()
        async with factory() as db:
            ex = ServiceExecution(
                user_id=uid, service_slug="s", workflow_name="song", status="pending"
            )
            db.add(ex)
            await db.commit()
            await db.refresh(ex)
            await engine.execute_workflow(
                db, ex, SERVICE, SERVICE["workflows"]["song"], {"voice": "warm"}
            )
            await db.refresh(ex)
            assert ex.status == "completed"
            assert "stub" in ex.result["write"]  # sortie texte de l'agent
            assert ex.result["render"]["audio_url"].endswith(".mp3")  # sortie du tool
            assert ex.result["output"]  # dernier texte d'agent, non vide
            steps = (
                await db.execute(
                    select(ExecutionStep)
                    .where(ExecutionStep.execution_id == ex.id)
                    .order_by(ExecutionStep.idx)
                )
            ).scalars().all()
            assert [s.name for s in steps] == ["write", "render"]
            assert all(s.status == "completed" for s in steps)
        await eng.dispose()
        dbpath.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_engine_marks_failed_on_unknown_tool():
    async def scenario():
        eng, factory, dbpath, uid = await _fresh_db()
        async with factory() as db:
            ex = ServiceExecution(
                user_id=uid, service_slug="s", workflow_name="broken", status="pending"
            )
            db.add(ex)
            await db.commit()
            await db.refresh(ex)
            await engine.execute_workflow(
                db, ex, SERVICE, SERVICE["workflows"]["broken"], {}
            )
            await db.refresh(ex)
            assert ex.status == "failed"
            assert ex.result["failed_step"] == "boom"
        await eng.dispose()
        dbpath.unlink(missing_ok=True)

    asyncio.run(scenario())


def test_credits_debit_refund_and_insufficient():
    async def scenario():
        eng, factory, dbpath, uid = await _fresh_db()
        async with factory() as db:
            assert await credits.get_balance(db, uid) == credits.INITIAL_CREDITS
            assert await credits.debit(db, uid, 3) is True
            assert await credits.get_balance(db, uid) == credits.INITIAL_CREDITS - 3
            await credits.refund(db, uid, 3)
            assert await credits.get_balance(db, uid) == credits.INITIAL_CREDITS
            # Solde insuffisant : rien n'est débité.
            assert await credits.debit(db, uid, 999) is False
            assert await credits.get_balance(db, uid) == credits.INITIAL_CREDITS
        await eng.dispose()
        dbpath.unlink(missing_ok=True)

    asyncio.run(scenario())
