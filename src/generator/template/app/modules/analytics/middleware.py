"""TrackingMiddleware — enregistrement des visites (Chap 13).

Chaque requête produit une `Visit` anonymisée (ip_hash, jamais l'IP en clair).
Liaison tardive de `database.SessionLocal` (testable). NOTE : pour un trafic
élevé, le livre déporte l'écriture hors du chemin de réponse (run_in_executor) ;
ici on l'attend pour rester simple et testable.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core import database
from app.core.config import get_settings
from app.modules.analytics.geoip import geolocate, hash_ip
from app.modules.analytics.models import Visit


class TrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        await self._store_visit(
            request.client.host if request.client else "",
            request.url.path,
        )
        return response

    async def _store_visit(self, ip: str, path: str) -> None:
        try:
            geo = geolocate(ip)
            async with database.SessionLocal() as db:
                db.add(
                    Visit(
                        ip_hash=hash_ip(ip, get_settings().secret_key),
                        country_code=geo["country_code"],
                        city=geo.get("city"),
                        path=path,
                    )
                )
                await db.commit()
        except Exception:
            # Le tracking ne doit jamais dégrader la requête.
            pass
