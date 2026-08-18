"""Point d'entrée FastAPI (spike).

Reproduit le pattern de chargement conditionnel du Chap 3 / Chap 5 :
- le core est toujours chargé ;
- chaque module n'est **importé qu'à l'intérieur du `if`** correspondant à son
  flag, garantissant qu'un module désactivé n'entre jamais dans `sys.modules`
  et ne coûte donc aucune RAM.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # DEV uniquement : crée les tables sans Alembic — le dev-compose n'a pas
    # d'étape `migrate`, on veut néanmoins une app qui tourne d'un `up`. La PROD
    # crée les tables via les migrations (service `migrate`), JAMAIS par
    # create_all — d'où le garde sur ENVIRONMENT.
    if settings.environment == "development":
        import app.core.models  # noqa: F401  (enregistre User)

        try:
            import app.domain.models  # noqa: F401  (tables métier scaffoldées)
        except ImportError:
            pass
        from app.core.database import Base, engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Les jobs agentic vivent dans des asyncio.Task : un redémarrage les emporte.
    # Au boot, personne ne tourne encore -> toute exécution pending/running est
    # orpheline : on la clôt en failed et on rembourse son coût persisté.
    if settings.module_agentic:
        from app.core.database import SessionLocal
        from app.modules.agentic.recovery import recover_orphan_executions

        await recover_orphan_executions(SessionLocal)
    yield


app = FastAPI(title=f"GitSky — {settings.project_name}", lifespan=lifespan)

# CORS : le frontend vit sur une AUTRE origine que l'API (localhost:5173 -> :8000
# en dev, domaine.com -> api.domaine.com en prod) et envoie le cookie refresh
# (credentials: "include"). Sans ce middleware, le navigateur bloque tout le flux
# d'auth — invisible en TestClient, fatal en réel. Origine unique et nommée :
# "*" est incompatible avec allow_credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

if settings.module_admin:
    from app.modules.admin import router as admin_router

    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

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

# --- Métier : le core inclut tout APIRouter exposé par app.domain.routers
# (scaffolding data_models/domain_routes, ou code métier du projet). Chaque
# routeur porte son propre prefix. Import optionnel : dans un projet généré,
# app/domain/routers.py existe (rendu depuis le .jinja) ; sans routeur métier,
# la boucle ne fait rien.
try:
    from app.domain import routers as _domain_routers  # noqa: E402
except ImportError:
    _domain_routers = None

if _domain_routers is not None:
    for _name in dir(_domain_routers):
        if _name.endswith("_router"):
            app.include_router(getattr(_domain_routers, _name))


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
            "admin": settings.module_admin,
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
