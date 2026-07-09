"""Routeur admin du module security (Chap 14).

Synthèse et journal des événements d'intrusion. Réservé aux administrateurs
(`require_admin`). Monté sous /api/admin/security par le core.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_admin
from app.core.database import get_db
from app.core.models import User
from app.modules.security.models import SecurityEvent
from app.modules.security.schemas import SecurityEventRead, SecuritySummary

router = APIRouter()


@router.get("/summary", response_model=SecuritySummary)
async def summary(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> SecuritySummary:
    total = (
        await db.execute(select(func.count()).select_from(SecurityEvent))
    ).scalar_one()
    rows = (
        await db.execute(
            select(SecurityEvent.severity, func.count()).group_by(
                SecurityEvent.severity
            )
        )
    ).all()
    return SecuritySummary(total=total, by_severity={sev: cnt for sev, cnt in rows})


@router.get("/events", response_model=list[SecurityEventRead])
async def events(
    severity: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[SecurityEvent]:
    stmt = select(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(limit)
    if severity is not None:
        stmt = stmt.where(SecurityEvent.severity == severity)
    result = await db.execute(stmt)
    return list(result.scalars().all())
