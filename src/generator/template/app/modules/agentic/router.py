"""Routeur du module agentic (Chap 15).

- GET  /services                : catalogue (public).
- GET  /services/{slug}         : détail d'un service.
- GET  /credits                 : solde de crédits de l'utilisateur.
- POST /services/{slug}/execute : exécute un workflow (auth).
    * workflow court (aperçu)  -> synchrone, renvoie `completed` + résultat ;
    * workflow dans `async_workflows` -> **submit-and-return** : crée un job
      `pending`, lance le pipeline en tâche de fond, rend la main tout de suite.
- GET  /executions/{id}         : suivi/polling d'une exécution (auth).

Monté sous /api/agent-services par le core. Le pipeline passe par `engine`.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.database import SessionLocal, get_db
from app.core.models import User
from app.modules.agentic import credits, engine
from app.modules.agentic.models import ServiceExecution
from app.modules.agentic.registry import get_service, load_services
from app.modules.agentic.schemas import (
    ExecuteRequest,
    ExecutionRead,
    ServiceSummary,
)

router = APIRouter()

# Références fortes aux jobs de fond : sans ça, asyncio peut les GC en plein vol.
_JOBS: set[asyncio.Task] = set()


@router.get("/services", response_model=list[ServiceSummary])
async def list_services() -> list[ServiceSummary]:
    return [
        ServiceSummary(
            slug=slug,
            name=svc.get("name", ""),
            description=svc.get("description", ""),
            category=svc.get("category", ""),
        )
        for slug, svc in load_services().items()
        if svc.get("enabled", True)
    ]


@router.get("/services/{slug}")
async def service_detail(slug: str) -> dict:
    service = get_service(slug)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service introuvable")
    return service


@router.get("/credits")
async def my_credits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {"balance": await credits.get_balance(db, user.id)}


@router.post("/services/{slug}/execute", response_model=ExecutionRead)
async def execute(
    slug: str,
    payload: ExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ServiceExecution:
    service = get_service(slug)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service introuvable")
    workflow = (service.get("workflows") or {}).get(payload.workflow_name)
    if workflow is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Workflow inconnu")

    is_async = payload.workflow_name in (service.get("async_workflows") or [])
    cost = int(service.get("cost_credits", 0)) if is_async else 0
    if cost and not await credits.debit(db, user.id, cost):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, "Crédits insuffisants"
        )

    execution = ServiceExecution(
        user_id=user.id,
        service_slug=slug,
        workflow_name=payload.workflow_name,
        status="pending",
        input_params=payload.parameters,
        result=None,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    if not is_async:
        # Workflow court (aperçu) : on exécute en ligne et on renvoie `completed`.
        await engine.execute_workflow(db, execution, service, workflow, payload.parameters)
        await db.refresh(execution)
        return execution

    # Workflow long : job de fond, on rend la main immédiatement (le client
    # suivra via GET /executions/{id}).
    task = asyncio.create_task(
        _run_job(execution.id, slug, payload.workflow_name, payload.parameters, user.id, cost)
    )
    _JOBS.add(task)
    task.add_done_callback(_JOBS.discard)
    return execution


async def _run_job(
    execution_id: int,
    slug: str,
    workflow_name: str,
    params: dict,
    user_id: int,
    cost: int,
) -> None:
    """Exécute un workflow long hors requête, dans sa propre session DB."""
    service = get_service(slug) or {}
    workflow = (service.get("workflows") or {}).get(workflow_name, [])
    async with SessionLocal() as db:
        execution = await db.get(ServiceExecution, execution_id)
        if execution is None:
            return
        try:
            await engine.execute_workflow(db, execution, service, workflow, params)
        except Exception:  # noqa: BLE001
            execution.status = "failed"
            await db.commit()
        if execution.status == "failed" and cost:
            await credits.refund(db, user_id, cost)


@router.get("/executions/{execution_id}", response_model=ExecutionRead)
async def get_execution(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ServiceExecution:
    execution = await db.get(ServiceExecution, execution_id)
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exécution introuvable")
    return execution
