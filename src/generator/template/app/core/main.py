"""Point d'entrée FastAPI (spike).

Reproduit le pattern de chargement conditionnel du Chap 3 / Chap 5 :
- le core est toujours chargé ;
- chaque module n'est **importé qu'à l'intérieur du `if`** correspondant à son
  flag, garantissant qu'un module désactivé n'entre jamais dans `sys.modules`
  et ne coûte donc aucune RAM.
"""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()

app = FastAPI(title=f"GitSky — {settings.project_name}")

# --- Core : SEO (Chap 10). Présent à tous les tiers, pas de flag MODULE_*.
# Monté à la racine : /sitemap.xml et /robots.txt doivent vivre à l'origine.
from app.core.seo import router as seo_router  # noqa: E402

app.include_router(seo_router, tags=["seo"])

# --- Modules optionnels : import à l'INTÉRIEUR du if (règle Chap 5 §3) ---

if settings.module_security_middleware:
    from app.modules.security import SecurityMiddleware
    from app.modules.security import router as security_router

    app.add_middleware(SecurityMiddleware)
    app.include_router(
        security_router, prefix="/api/admin/security", tags=["security"]
    )

if settings.module_auth:
    from app.core.auth import router as auth_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

if settings.module_analytics:
    from app.modules.analytics import TrackingMiddleware
    from app.modules.analytics import router as analytics_router

    app.add_middleware(TrackingMiddleware)
    app.include_router(
        analytics_router, prefix="/api/admin/analytics", tags=["analytics"]
    )

if settings.module_agentic:
    from app.modules.agentic import router as agentic_router

    app.include_router(agentic_router, prefix="/api/agent-services")

if settings.module_tutorials:
    from app.modules.tutorials import router as tutorials_router

    app.include_router(tutorials_router, prefix="/api/content", tags=["tutorials"])

if settings.module_onboarding:
    from app.modules.onboarding import router as onboarding_router

    app.include_router(onboarding_router, prefix="/api/onboarding", tags=["onboarding"])

# Monetization : le webhook (dans shop_router) doit exister dès qu'un des deux
# flags est actif ; admin réservé à la boutique, subscription à son flag.
if settings.module_monetization_shop or settings.module_monetization_subscription:
    from app.modules.monetization import shop_router

    app.include_router(shop_router, prefix="/api/shop", tags=["monetization"])

if settings.module_monetization_shop:
    from app.modules.monetization import admin_router as shop_admin_router

    app.include_router(
        shop_admin_router, prefix="/api/admin/shop", tags=["monetization"]
    )

if settings.module_monetization_subscription:
    from app.modules.monetization import subscription_router

    app.include_router(
        subscription_router, prefix="/api/subscription", tags=["monetization"]
    )

if settings.module_fleet:
    from app.modules.fleet import router as fleet_router

    app.include_router(fleet_router, prefix="/api/fleet", tags=["fleet"])


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    # Le monitoring de disponibilité (UptimeRobot, Chap 23 §4.1) tape ici. Sans
    # vérif DB, /health répondrait 200 avec une base morte : l'incident passerait
    # inaperçu. On teste la connexion et on renvoie 503 si elle échoue — Traefik
    # et le fleet dashboard voient alors le conteneur comme non sain.
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {
        "status": "ok",
        "database": "ok",
        "project": settings.project_name,
        "tier": settings.gitsky_tier,
        "modules": {
            "auth": settings.module_auth,
            "analytics": settings.module_analytics,
            "security_middleware": settings.module_security_middleware,
            "agentic": settings.module_agentic,
            "tutorials": settings.module_tutorials,
            "onboarding": settings.module_onboarding,
            "monetization_shop": settings.module_monetization_shop,
            "monetization_subscription": settings.module_monetization_subscription,
            "fleet": settings.module_fleet,
        },
    }
