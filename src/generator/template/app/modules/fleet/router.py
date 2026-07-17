"""Routeur du module fleet (Chap 19).

- POST /projects/register : inscription d'un projet (appelé par le générateur).
  Un projet « n'existe » dans la flotte que s'il est enregistré ici.
- GET  /projects           : grille des projets (réservé à l'opérateur).
Monté sous /api/fleet par le core (module_fleet, app dashboard uniquement).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.core.auth.dependencies import require_admin
from app.core.database import get_db
from app.core.models import User
from app.modules.fleet import health_monitor, kill_check, publish
from app.modules.fleet.models import FleetLifecycleEvent, Project
from app.modules.fleet.schemas import (
    HealthSweepRequest,
    HealthSweepResult,
    KillCheckMetrics,
    KillCheckResult,
    ProjectRegister,
    ProjectRead,
    PromoteRequest,
    PromoteResult,
)

router = APIRouter()

# Verdict -> (nouveau statut projet ou None, type d'événement journalisé ou None).
_VERDICT_ACTIONS: dict[str, tuple[str | None, str | None]] = {
    kill_check.HEALTHY: (None, None),
    kill_check.PENDING_KILL: ("pending_kill", "pending_kill"),
    kill_check.KILL_NOW: ("killed", "killed"),
    kill_check.MANUAL_REVIEW: (None, "manual_review"),
}


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


@router.post("/projects/{name}/kill-check", response_model=KillCheckResult)
async def run_kill_check(
    name: str,
    metrics: KillCheckMetrics,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> KillCheckResult:
    project = (
        await db.execute(select(Project).where(Project.name == name))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable"
        )

    verdict = kill_check.evaluate(project.tier, kill_check.Metrics(**metrics.model_dump()))
    new_status, event_type = _VERDICT_ACTIONS[verdict]

    if new_status is not None:
        project.status = new_status
    if event_type is not None:
        db.add(
            FleetLifecycleEvent(
                project_name=project.name,
                event_type=event_type,
                tier=project.tier,
                reason=f"kill_check verdict={verdict}",
            )
        )
    await db.commit()
    return KillCheckResult(
        project=project.name, tier=project.tier, verdict=verdict, status=project.status
    )


@router.post("/projects/health-sweep", response_model=HealthSweepResult)
async def health_sweep(
    payload: HealthSweepRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> HealthSweepResult:
    # Le poller (cron 60 s) poste les derniers succès /health de la flotte ;
    # le dashboard journalise les transitions deployment_failed/recovered.
    now = payload.now or datetime.now(timezone.utc)
    changed = await health_monitor.record_health_sweep(db, payload.last_success, now)
    return HealthSweepResult(**changed)


@router.post("/projects/{name}/promote", response_model=PromoteResult)
async def promote(
    name: str,
    payload: PromoteRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PromoteResult:
    project = (
        await db.execute(select(Project).where(Project.name == name))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Projet introuvable"
        )

    decision = publish.evaluate_promotion(
        project.publish_status,
        project.tier,
        payload.guardrails_pass,
        payload.human_approved,
    )
    if decision["allowed"]:
        project.publish_status = decision["target"]
        db.add(
            FleetLifecycleEvent(
                project_name=project.name,
                event_type=f"publish_{decision['target']}",
                tier=project.tier,
                reason=decision["reason"],
            )
        )
    await db.commit()
    return PromoteResult(
        project=project.name,
        publish_status=project.publish_status,
        allowed=decision["allowed"],
        reason=decision["reason"],
    )
