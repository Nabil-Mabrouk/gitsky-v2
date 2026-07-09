# L'API Core et les Contrats de Modules

## Introduction

L'API du template GitSky suit le même découpage en couches que le backend : le **core** définit les patterns et les contrats communs, tandis que chaque **module** apporte ses propres endpoints. Ce chapitre couvre les patterns partagés — validation Pydantic, chargement dynamique des routers, contrats d'interface — ainsi qu'une vue d'ensemble du framework agentic IA (dont le détail est en Chap 15).

## Validation des Données avec Pydantic

FastAPI utilise **Pydantic** pour valider les données entrantes et sortantes. Chaque routeur — core ou module — définit ses schémas dans un fichier `schemas.py` :

```python
# app/modules/onboarding/schemas.py — exemple
from pydantic import BaseModel

class OnboardingAnswer(BaseModel):
    flow_id: str
    answers: dict[str, str]

class OnboardingResult(BaseModel):
    title: str
    description: str
    score: int
    profile: str
    label: str
```

Grâce à ces schémas, FastAPI génère automatiquement la documentation Swagger et rejette toute requête mal formée avant même qu'elle n'atteigne la logique métier.

## Contrat d'Interface d'un Module

Un module qui apporte des endpoints à l'API doit exposer une interface minimale que le core sait détecter :

```python
# app/modules/mon_module/__init__.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
async def status():
    return {"module": "mon_module", "ok": True}
```

Le core, dans `main.py`, importe conditionnellement ce `router` selon le flag `MODULE_MON_MODULE` (voir Chap 3). Aucun couplage direct n'existe entre le core et le module au-delà de ce contrat.

## Chargement Dynamique des Routers

Le pattern d'inclusion conditionnelle est central :

```python
# app/core/main.py — pattern répété pour chaque module
if settings.module_analytics:
    from app.modules.analytics import router as analytics_router
    app.include_router(analytics_router, prefix="/api/analytics")
```

Trois règles à respecter :

1. **Import à l'intérieur du `if`** — sinon le module est chargé même s'il est désactivé.
2. **Préfixe cohérent** — toujours `/api/<nom-module>` pour la lisibilité.
3. **Un seul router par module** — les sous-routers internes du module sont agrégés dans son `__init__.py`.

## Services Transverses : Clients Partagés

Certains services ne sont pas des routers exposés par un module — ce sont des **clients partagés** utilisés par plusieurs modules ou par la couche domaine :

| Client | Rôle | Utilisé par |
|---|---|---|
| `landing_collector_client` | Poste un formulaire de landing dans la base centrale de la flotte | Tier T0 sans DB propre |
| `llm_proxy_client` | Appelle un LLM via le proxy partagé (quota et logs par projet) | Framework agentic, tout module IA |
| `geoip_client` | Résout une IP en pays/ville depuis le service GeoIP mutualisé | Module analytics, module security |
| `smtp_client` | Envoie un email transactionnel via le relais SMTP partagé | Onboarding, monetization, notifications kill |

Ces clients vivent dans `app/shared/clients/` et sont partagés à travers le core. Leur implémentation et leur configuration côté flotte sont détaillées au Chap 18 (Services partagés).

## Aperçu du Framework Agentic IA

Le module `agentic` transforme un projet GitSky en écosystème d'automatisation multi-agents. Son activation reste optionnelle (`MODULE_AGENTIC=true`) car il apporte une empreinte non négligeable — modèles, orchestrator, tool registry, memory system, guardrails.

Endpoints principaux exposés par le module :

```python
GET  /api/agent-services/services
POST /api/agent-services/services/{service_slug}/execute
GET  /api/agent-services/executions/{execution_id}
```

Le détail de l'architecture agentic est présenté au Chap 15, et celui du LLM proxy partagé (mutualisation des clés API, quotas par projet, logs) au Chap 18.

---

*Le socle API est en place, avec ses patterns communs et son contrat d'interface pour les modules. Dans la partie suivante, nous construisons l'interface utilisateur pour interagir avec ce backend modulaire.*
