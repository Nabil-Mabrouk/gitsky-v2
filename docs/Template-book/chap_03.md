# Initialisation du Backend avec FastAPI

## Pourquoi FastAPI ?

Pour le template **GitSky**, nous avons besoin d'un backend capable de gérer des tâches asynchrones, une validation de données stricte, une documentation automatique, et surtout **d'activer ou désactiver des modules entiers de fonctionnalités selon les besoins de chaque projet**. FastAPI s'est imposé comme le choix naturel grâce à :

1.  **Performance :** Basé sur Starlette et Pydantic, il est l'un des frameworks Python les plus rapides.
2.  **Asynchronisme natif :** Crucial pour les appels à l'IA ou les traitements de données lourds sans bloquer l'API.
3.  **Type Safety :** Utilisation intensive des hints Python pour réduire les bugs et améliorer l'auto-complétion.
4.  **Modularité par inclusion de routers :** Permet le chargement dynamique de modules selon la configuration, sans surcoût mémoire pour les modules inactifs.

## Structure d'un Projet Professionnel

L'architecture GitSky repose sur trois couches distinctes : `core`, `modules`, `domain`. Cette séparation est ce qui permet à un même code base de porter n'importe quelle combinaison du catalogue de modules présenté au chapitre précédent.

```text
backend/
├── app/
│   ├── core/                   # Toujours présent — socle commun à tous les projets
│   │   ├── auth/               # JWT + gestion des rôles utilisateur
│   │   ├── admin_shell/        # Coquille admin extensible
│   │   ├── database.py         # Session et moteur SQLAlchemy
│   │   ├── config.py           # Paramètres Pydantic Settings + flags module
│   │   ├── main.py             # Initialisation FastAPI + chargement des modules
│   │   ├── models.py           # Modèles core (User, Role)
│   │   └── seo.py              # Composants SEO de base
│   ├── modules/                # Modules optionnels activables par MODULE_*
│   │   ├── analytics/          # GeoIP tracking + world map
│   │   ├── onboarding/         # Profilage dynamique
│   │   ├── tutorials/          # Système de contenu pédagogique
│   │   ├── security/           # SecurityMiddleware
│   │   ├── i18n/               # Chargement des locales serveur
│   │   ├── agentic/            # Framework multi-agents IA
│   │   └── monetization/       # Stripe boutique + abonnements
│   ├── domain/                 # Métier spécifique au projet
│   │   ├── models.py           # Tables métier
│   │   ├── routers.py          # Endpoints métier
│   │   └── schemas.py          # Validation Pydantic métier
│   └── shared/                 # Utilitaires transverses
│       └── clients/            # Clients HTTP, LLM proxy, SMTP…
├── alembic/                    # Migrations
│   ├── core/                   # Chaîne de migrations du core
│   └── modules/                # Chaîne par module (activée conditionnellement)
├── uploads/                    # Stockage des médias
├── requirements.txt            # Dépendances Python
└── alembic.ini                 # Configuration des migrations
```

### Trois Couches, Trois Responsabilités

- **`core/`** ne dépend que de la stack (FastAPI, SQLAlchemy, Pydantic). Il ne connaît ni les modules ni le domaine — mais il expose les hooks nécessaires pour les charger.
- **`modules/`** dépend uniquement du core. Chaque module s'active ou se désactive via un flag `MODULE_*` sans que ni le core ni les autres modules n'aient besoin d'être modifiés.
- **`domain/`** dépend du core et éventuellement de certains modules. C'est la couche unique par projet, produite par le générateur `create-gitsky-project` (voir Chap 17).

## Le Système de Modules

Un module est un dossier isolé qui contient tout ce qu'il apporte : modèles SQLAlchemy, routeurs FastAPI, schémas Pydantic, migrations Alembic. À l'initialisation de l'API, `main.py` charge dynamiquement les modules activés :

```python
# app/core/main.py — extrait
from fastapi import FastAPI
from app.core.config import get_settings
from app.core import auth, admin_shell

settings = get_settings()
app = FastAPI(title=f"GitSky — {settings.project_name}")

# Chargement systématique du core
app.include_router(auth.router, prefix="/api/auth")
app.include_router(admin_shell.router, prefix="/api/admin")

# Chargement conditionnel des modules
if settings.module_analytics:
    from app.modules.analytics import router as analytics_router
    app.include_router(analytics_router, prefix="/api/analytics")

if settings.module_onboarding:
    from app.modules.onboarding import router as onboarding_router
    app.include_router(onboarding_router, prefix="/api/onboarding")

if settings.module_agentic:
    from app.modules.agentic import router as agentic_router
    app.include_router(agentic_router, prefix="/api/agent-services")

# … idem pour les autres modules
```

Trois propriétés découlent de ce système :

1.  **Aucun surcoût mémoire pour un module inactif** — son code n'est jamais importé.
2.  **Aucune migration Alembic inutile** — la chaîne de migrations d'un module désactivé n'est simplement pas incluse dans l'environnement Alembic.
3.  **Extensibilité sans modification du core** — ajouter un nouveau module se fait en respectant un contrat d'interface simple (`router`, `models`, `migrations/`).

## Configuration Centralisée avec Pydantic Settings

Nous utilisons `pydantic-settings` pour charger et valider nos variables d'environnement. Le `Settings` centralise à la fois les paramètres de projet et les flags de modules :

```python
# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    project_name: str
    secret_key: str
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    database_url: str

    # Modules — catalogue à plat, chacun désactivé par défaut et indépendant
    # des autres. auth et SEO ne figurent pas ici : ce sont des capacités core,
    # toujours montées, sans flag (voir Chap 2).
    module_admin: bool = False
    module_analytics: bool = False
    module_onboarding: bool = False
    module_tutorials: bool = False
    module_security_middleware: bool = False
    module_i18n: bool = False
    module_agentic: bool = False
    module_monetization_shop: bool = False
    module_monetization_subscription: bool = False
    module_fleet: bool = False   # réservé à l'app fleet dashboard elle-même

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

Cela garantit qu'une variable manquante (`SECRET_KEY`, `DATABASE_URL`, `PROJECT_NAME`) empêche l'application de démarrer, plutôt que de la laisser tourner dans un état incohérent.

## Connexion à la Base de Données (SQLAlchemy)

Chaque projet GitSky possède sa **propre base de données PostgreSQL**, dès sa création — cette isolation est ce qui permet à un projet de vivre, d'activer ou de désactiver des modules, ou d'être archivé sans impacter les autres. La connexion utilise SQLAlchemy en mode **asynchrone** (moteur `asyncpg` en production) et fournit une session fraîche à chaque requête via le pattern « Dependency Injection ».

```python
# app/core/database.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)
Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

L'URL de connexion prend la forme `postgresql+asyncpg://user:pass@db:5432/dbname`
en production. Les endpoints qui consomment cette session sont eux-mêmes `async`
et utilisent `await` pour chaque opération de base (`await db.execute(...)`,
`await db.commit()`).

## Le Point d'Entrée : `main.py`

Le fichier `main.py` orchestre l'application, applique les middlewares (CORS, éventuellement SecurityMiddleware), et inclut les routeurs core puis les modules activés :

```python
# app/core/main.py — version complète
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core import auth, admin_shell

settings = get_settings()
app = FastAPI(title=f"GitSky — {settings.project_name}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SecurityMiddleware conditionnel (module)
if settings.module_security_middleware:
    from app.modules.security import SecurityMiddleware
    app.add_middleware(SecurityMiddleware)

# Routers core (toujours actifs)
app.include_router(auth.router, prefix="/api/auth")
app.include_router(admin_shell.router, prefix="/api/admin")

# Routers modules (chargés selon les flags)
if settings.module_analytics:
    from app.modules.analytics import router as analytics_router
    app.include_router(analytics_router, prefix="/api/analytics")

# … idem pour les autres modules

@app.get("/health")
async def health():
    return {"status": "ok", "project": settings.project_name}
```

## Lancer le Backend

Grâce à Docker Compose, le lancement est automatique. Le point d'entrée Uvicorn reste identique quelle que soit la combinaison de modules activés :

```bash
uvicorn app.core.main:app --host 0.0.0.0 --port 8000 --reload
```

Le flag `--reload` est utilisé en développement uniquement. En production, Gunicorn orchestre plusieurs workers Uvicorn (voir Chap 21).

---

*Le squelette du backend est en place. Dans le prochain chapitre, nous détaillons la modélisation des données — en distinguant explicitement les modèles du core (toujours présents) et les modèles apportés par chaque module optionnel.*
