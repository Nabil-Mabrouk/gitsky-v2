"""Faux module `agentic` (spike).

Le module le plus lourd du profil T2 dans le livre (orchestrator, tool registry,
memory, guardrails — Chap 15). Ici réduit à son contrat `router`. Sa vraie
empreinte RAM viendra de ses dépendances réelles, absentes du spike.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status() -> dict:
    return {"module": "agentic", "ok": True}
