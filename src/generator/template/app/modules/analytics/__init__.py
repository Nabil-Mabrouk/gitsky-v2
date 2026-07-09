"""Faux module `analytics` (spike).

Respecte le contrat d'interface minimal du Chap 5 : exposer un `router`.
Le core ne connaît rien de ce module au-delà de ce `router`.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status() -> dict:
    return {"module": "analytics", "ok": True}
