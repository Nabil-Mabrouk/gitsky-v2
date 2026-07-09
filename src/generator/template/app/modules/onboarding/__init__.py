"""Module `onboarding` — profilage dynamique (Chap 12).

Contrat : expose `router`. Moteur de scoring piloté par flows JSON.
"""

from app.modules.onboarding.router import router

__all__ = ["router"]
