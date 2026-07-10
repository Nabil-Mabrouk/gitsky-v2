"""Module `security` — détection d'intrusion (Chap 14).

Contrairement aux autres modules, `security` apporte à la fois un middleware
(`SecurityMiddleware`, journalisation) et un routeur admin (`router`, synthèse
et journal). Le core installe les deux quand MODULE_SECURITY_MIDDLEWARE=true.
"""

from app.modules.security.middleware import SecurityMiddleware
from app.modules.security.router import router

__all__ = ["SecurityMiddleware", "router"]
