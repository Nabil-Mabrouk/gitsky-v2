"""Module métier `tutorials` — université virtuelle (Chap 11).

Exemple canonique de module GitSky : modèles + schémas + routeur + chaîne
Alembic dédiée, activable via MODULE_TUTORIALS. Contrat : exporte `router`.
"""

from app.modules.tutorials.router import router

__all__ = ["router"]
