"""Module `analytics` — tracking anonymisé RGPD (Chap 13).

Apporte un middleware de tracking (`TrackingMiddleware`) et un routeur admin
d'agrégation (`router`). Le core installe les deux quand MODULE_ANALYTICS=true.
"""

from app.modules.analytics.middleware import TrackingMiddleware
from app.modules.analytics.router import router

__all__ = ["TrackingMiddleware", "router"]
