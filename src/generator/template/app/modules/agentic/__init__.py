"""Module `agentic` — framework de services IA (Chap 15).

Contrat : expose `router`. Services déclarés en YAML, exécutions tracées, appels
LLM via le proxy partagé (client stubbé pour l'instant).
"""

from app.modules.agentic.router import router

__all__ = ["router"]
