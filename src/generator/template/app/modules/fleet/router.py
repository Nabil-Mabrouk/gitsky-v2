"""Routeur du module fleet (Chap 19).

- POST /projects/register : inscription d'un projet (appelé par le générateur).
  Un projet « n'existe » dans la flotte que s'il est enregistré ici.
- GET  /projects           : grille des projets (réservé à l'opérateur).
Monté sous /api/fleet par le core (module_fleet, app dashboard uniquement).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import require_admin
from app.core.database import get_db
from app.core.models import User
from app.modules.fleet.models import FleetLifecycleEvent, Project
from app.modules.fleet.schemas import ProjectRegister, ProjectRead

router = APIRouter()


@router.post("/projects/register", response_model=ProjectRead)
async def register_project(
    payload: ProjectRegister, db: AsyncSession = Depends(get_db)
) -> Project:
    existing = (
        await db.execute(select(Project).where(Project.name == payload.name))
    ).scalar_one_or_none()
    if existing is None:
        project = Project(
            name=payload.name,
            tier=payload.tier,
            domain=payload.domain,
            template_version=payload.template_version,
        )
        db.add(project)
        db.add(
            FleetLifecycleEvent(
                project_name=payload.name, event_type="born", tier=payload.tier
            )
        )
    else:
        existing.tier = payload.tier
        existing.domain = payload.domain
        existing.template_version = payload.template_version
        project = existing
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(
    status: str | None = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    stmt = select(Project).order_by(Project.name)
    if status is not None:
        stmt = stmt.where(Project.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())
