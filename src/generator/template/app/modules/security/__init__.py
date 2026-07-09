"""Faux module `security` (spike).

Contrairement aux autres modules, `security` s'installe comme middleware
(Chap 3 §main.py) plutôt que comme router. On prouve son activation via un
en-tête HTTP ajouté à chaque réponse.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-GitSky-Security"] = "on"
        return response
