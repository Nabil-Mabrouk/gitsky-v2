"""Point d'entrée FastAPI (spike).

Reproduit le pattern de chargement conditionnel du Chap 3 / Chap 5 :
- le core est toujours chargé ;
- chaque module n'est **importé qu'à l'intérieur du `if`** correspondant à son
  flag, garantissant qu'un module désactivé n'entre jamais dans `sys.modules`
  et ne coûte donc aucune RAM.
"""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=f"GitSky — {settings.project_name}")

# --- Modules optionnels : import à l'INTÉRIEUR du if (règle Chap 5 §3) ---

if settings.module_security_middleware:
    from app.modules.security import SecurityMiddleware

    app.add_middleware(SecurityMiddleware)

if settings.module_auth:
    from app.core.auth import router as auth_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

if settings.module_analytics:
    from app.modules.analytics import router as analytics_router

    app.include_router(analytics_router, prefix="/api/analytics")

if settings.module_agentic:
    from app.modules.agentic import router as agentic_router

    app.include_router(agentic_router, prefix="/api/agent-services")

if settings.module_tutorials:
    from app.modules.tutorials import router as tutorials_router

    app.include_router(tutorials_router, prefix="/api/content", tags=["tutorials"])


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "project": settings.project_name,
        "tier": settings.gitsky_tier,
        "modules": {
            "auth": settings.module_auth,
            "analytics": settings.module_analytics,
            "security_middleware": settings.module_security_middleware,
            "agentic": settings.module_agentic,
            "tutorials": settings.module_tutorials,
        },
    }
