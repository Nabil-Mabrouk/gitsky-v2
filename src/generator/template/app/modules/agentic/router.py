"""Routeur du module agentic (Chap 15).

- GET  /services              : catalogue (public).
- GET  /services/{slug}       : détail d'un service.
- POST /services/{slug}/execute : exécute un workflow (auth) et trace l'exécution.
- GET  /executions/{id}       : suivi d'une exécution (auth).
Monté sous /api/agent-services par le core. L'exécution passe par le client LLM
(STUB — à connecter au proxy partagé).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.models import User
from app.modules.agentic.llm_client import call_llm
from app.modules.agentic.models import ServiceExecution
from app.modules.agentic.registry import get_service, load_services
from app.modules.agentic.schemas import (
    ExecuteRequest,
    ExecutionRead,
    ServiceSummary,
)

router = APIRouter()


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service introuvable"
        )
    return service


@router.post("/services/{slug}/execute", response_model=ExecutionRead)
async def execute(
    slug: str,
    payload: ExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ServiceExecution:
    service = get_service(slug)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Service introuvable"
        )

    # Exécution minimale : un appel LLM (stub) avec le premier agent du service.
    agent = (service.get("agents") or [{}])[0]
    output = call_llm(
        agent.get("model", "claude-sonnet-4-6"),
        [
            {"role": "system", "content": agent.get("system_prompt", "")},
            {"role": "user", "content": str(payload.parameters)},
        ],
        agent.get("temperature", 0.3),
    )

    execution = ServiceExecution(
        user_id=user.id,
        service_slug=slug,
        workflow_name=payload.workflow_name,
        status="completed",
        input_params=payload.parameters,
        result={"output": output},
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


@router.get("/executions/{execution_id}", response_model=ExecutionRead)
async def get_execution(
    execution_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ServiceExecution:
    execution = await db.get(ServiceExecution, execution_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exécution introuvable"
        )
    return execution
