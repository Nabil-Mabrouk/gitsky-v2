"""API du landing collector (Chap 18).

- POST /leads                : une landing T0 poste une capture d'email.
- GET  /leads/{project}/stats : le fleet dashboard lit le funnel du projet.

Les tables sont créées au démarrage (service minimal, pas d'Alembic).
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
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


@app.get("/leads/{project}/stats", response_model=LeadStats)
async def project_stats(
    project: str, db: AsyncSession = Depends(get_session)
) -> LeadStats:
    signups = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.project == project)
        )
    ).scalar_one()
    return LeadStats(project=project, signups=signups)
