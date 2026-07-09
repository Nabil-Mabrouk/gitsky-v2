"""Routeur admin du module analytics (Chap 13).

Agrégations pour le dashboard : provenance (world), séries temporelles
(timeline), top des URLs (paths). Réservé aux administrateurs. Monté sous
/api/admin/analytics par le core.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_admin
from app.core.database import get_db
from app.core.models import User
from app.modules.analytics.models import Visit
from app.modules.analytics.schemas import CountryCount, DayCount, PathCount

router = APIRouter()


def _cutoff(days: int) -> datetime:
    # Naïf (UTC) pour comparer proprement avec created_at côté SQLite.
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


@router.get("/world", response_model=list[CountryCount])
async def world(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[CountryCount]:
    rows = (
        await db.execute(
            select(Visit.country_code, func.count())
            .where(Visit.created_at >= _cutoff(days))
            .group_by(Visit.country_code)
        )
    ).all()
    return [CountryCount(country_code=code, visits=n) for code, n in rows]


@router.get("/paths", response_model=list[PathCount])
async def paths(
    days: int = 30,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[PathCount]:
    rows = (
        await db.execute(
            select(Visit.path, func.count().label("n"))
            .where(Visit.created_at >= _cutoff(days))
            .group_by(Visit.path)
            .order_by(func.count().desc())
            .limit(limit)
        )
    ).all()
    return [PathCount(path=path, visits=n) for path, n in rows]


@router.get("/timeline", response_model=list[DayCount])
async def timeline(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[DayCount]:
    day = func.date(Visit.created_at)
    rows = (
        await db.execute(
            select(day, func.count())
            .where(Visit.created_at >= _cutoff(days))
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [DayCount(date=str(d), visits=n) for d, n in rows]
