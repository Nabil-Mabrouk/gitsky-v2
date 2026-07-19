"""SecurityMiddleware — détection d'intrusion applicative (Chap 14).

Philosophie : **journaliser, jamais bloquer**. Chaque requête est inspectée par
les détecteurs ; une détection produit un `SecurityEvent` en base, mais la
requête suit son cours normalement (le blocage est délégué à Traefik/fail2ban).
La journalisation ne doit jamais casser la requête.
"""

from urllib.parse import unquote_plus

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core import database
from app.modules.security.detectors import detect_event
from app.modules.security.models import SecurityEvent

# Endpoints d'infrastructure (poller fleet, crawlers SEO) : hors radar — le
# blocage réseau est le rôle de Traefik/fail2ban, et journaliser chaque poll
# /health noierait les vraies détections.
EXCLUDED_PATHS: frozenset[str] = frozenset(
    {"/health", "/robots.txt", "/sitemap.xml"}
)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)
        # Décode la query : un attaquant peut URL-encoder sa charge (%27 -> ').
        event = detect_event(
            request.url.path,
            request.headers.get("user-agent"),
            unquote_plus(request.url.query),
        )
        if event is not None:
            await self._log(event, request)
        # Ne bloque JAMAIS : la réponse suit son cours.
        return await call_next(request)

    async def _log(self, event: dict, request: Request) -> None:
        try:
            async with database.SessionLocal() as db:  # liaison tardive (testable)
                db.add(
                    SecurityEvent(
                        event_type=event["event_type"],
                        severity=event["severity"],
                        ip_address=request.client.host if request.client else None,
                        path=request.url.path,
                        user_agent=request.headers.get("user-agent"),
                        details=event["details"],
                    )
                )
                await db.commit()
        except Exception:
            # La défense ne doit jamais dégrader la disponibilité.
            pass
