"""Portefeuille de crédits (Chap 15/16) — minimal.

Une génération payante débite le solde de l'utilisateur ; un échec le rembourse.
Un compte est créé à la volée avec un solde d'essai. Volontairement simple :
le vrai rechargement passe par `monetization` (achat de packs de crédits).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agentic.models import CreditAccount

INITIAL_CREDITS = 10


async def _get_or_create(db: AsyncSession, user_id: int) -> CreditAccount:
    account = (
        await db.execute(select(CreditAccount).where(CreditAccount.user_id == user_id))
    ).scalar_one_or_none()
    if account is None:
        account = CreditAccount(user_id=user_id, balance=INITIAL_CREDITS)
        db.add(account)
        await db.commit()
        await db.refresh(account)
    return account


async def get_balance(db: AsyncSession, user_id: int) -> int:
    return (await _get_or_create(db, user_id)).balance


async def debit(db: AsyncSession, user_id: int, amount: int) -> bool:
    """Débite `amount` si le solde suffit. Renvoie False sinon (rien débité)."""
    account = await _get_or_create(db, user_id)
    if account.balance < amount:
        return False
    account.balance -= amount
    await db.commit()
    return True


async def refund(db: AsyncSession, user_id: int, amount: int) -> None:
    account = await _get_or_create(db, user_id)
    account.balance += amount
    await db.commit()
