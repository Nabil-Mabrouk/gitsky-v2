"""Atomicité du portefeuille de crédits (durcissement).

`debit` faisait lecture-modification-écriture : deux requêtes simultanées
lisaient le même solde et le débitaient chacune (double dépense — deux
générations payées une seule fois). Contrat : le débit est un UPDATE
conditionnel (`balance >= amount`) — sous concurrence, un seul gagne et le
solde ne devient jamais négatif.
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

import app.core.models  # noqa: E402,F401
import app.modules.agentic.models  # noqa: E402,F401
from app.core.auth.security import hash_password  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.models import User  # noqa: E402
from app.modules.agentic import credits  # noqa: E402
from app.modules.agentic.models import CreditAccount  # noqa: E402

_DB_FILE = Path(tempfile.gettempdir()) / f"gitsky_credits_{os.getpid()}.db"
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


async def _set_balance(value: int) -> None:
    async with factory() as db:
        await credits._get_or_create(db, SEED["user_id"])
        account = (
            await db.execute(
                select(CreditAccount).where(CreditAccount.user_id == SEED["user_id"])
            )
        ).scalar_one()
        account.balance = value
        await db.commit()


def test_refused_debit_leaves_balance_untouched():
    async def scenario():
        await _set_balance(3)
        async with factory() as db:
            assert await credits.debit(db, SEED["user_id"], 5) is False
        return await _balance()

    assert asyncio.run(scenario()) == 3


def test_concurrent_debits_cannot_double_spend():
    async def scenario():
        # Solde 10, deux débits de 8 en parallèle : un seul doit passer.
        await _set_balance(10)
        async with factory() as db1, factory() as db2:
            results = await asyncio.gather(
                credits.debit(db1, SEED["user_id"], 8),
                credits.debit(db2, SEED["user_id"], 8),
            )
        return results, await _balance()

    results, balance = asyncio.run(scenario())
    assert sorted(results) == [False, True], (
        f"double dépense : {results} (les deux débits ont lu le même solde)"
    )
    assert balance == 2
    assert balance >= 0


def test_refund_restores_balance():
    async def scenario():
        await _set_balance(2)
        async with factory() as db:
            await credits.refund(db, SEED["user_id"], 4)
        return await _balance()

    assert asyncio.run(scenario()) == 6
