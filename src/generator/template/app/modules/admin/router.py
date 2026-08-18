"""Routeur du module admin (Chap 9).

Un seul endpoint : la découverte des modules actifs, consommée par
AdminLayout côté frontend pour construire dynamiquement sa sidebar sans
dupliquer la logique de résolution de tier déjà faite par Settings.
"""

from fastapi import APIRouter, Depends

from app.core.auth.dependencies import require_admin
from app.core.config import MODULE_FLAGS, get_settings
from app.core.models import User

router = APIRouter()


@router.get("/modules")
async def list_modules(_admin: User = Depends(require_admin)) -> dict[str, bool]:
    settings = get_settings()
    return {
        flag.removeprefix("module_"): bool(getattr(settings, flag))
        for flag in MODULE_FLAGS
    }
