"""API du landing collector (Chap 18).

- POST /leads                : une landing T0 poste une capture d'email.
- GET  /leads/{project}/stats : le fleet dashboard lit le funnel du projet.

Les tables sont créées au démarrage (service minimal, pas d'Alembic).
"""

import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from landing_collector.database import create_tables, get_session
from landing_collector.models import Lead
from landing_collector.schemas import LeadIn, LeadStats


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Landing Collector", lifespan=lifespan)


@app.post("/leads")
async def collect_lead(lead: LeadIn, db: AsyncSession = Depends(get_session)) -> dict:
    db.add(
        Lead(
            project=lead.project,
            email=lead.email,
            source=lead.source,
            utm_campaign=lead.utm_campaign,
        )
    )
    await db.commit()
    return {"ok": True}


async def verify_stats_token(
    x_collector_token: str | None = Header(default=None),
) -> None:
    """Garde de lecture des stats (durcissement, même sémantique que fleet).

    La CAPTURE (/leads) reste publique — les landings T0 postent sans secret.
    La LECTURE du funnel, elle, est réservée au fleet dashboard : token
    configuré -> header exigé ; absent -> ouvert en dev, refus en production.
    """
    expected = os.environ.get("COLLECTOR_STATS_TOKEN", "")
    if not expected:
        if os.environ.get("ENVIRONMENT", "").lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="COLLECTOR_STATS_TOKEN non configuré",
            )
        return
    if x_collector_token is None or not secrets.compare_digest(
        x_collector_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide"
        )


@app.get(
    "/leads/{project}/stats",
    response_model=LeadStats,
    dependencies=[Depends(verify_stats_token)],
)
async def project_stats(
    project: str, db: AsyncSession = Depends(get_session)
) -> LeadStats:
    signups = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.project == project)
        )
    ).scalar_one()
    return LeadStats(project=project, signups=signups)
