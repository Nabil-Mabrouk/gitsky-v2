"""Module `admin` — shell d'administration (Chap 9).

Expose GET /modules, la découverte des flags MODULE_* pour le frontend
(AdminLayout construit sa sidebar dessus). Contrat : exporte `router`.
"""

from app.modules.admin.router import router

__all__ = ["router"]
