# Module Analytics : GeoIP et Visualisation

## Introduction

> **Écart au livre (Phase 6)** : ce chapitre présentait auparavant le module `analytics` comme activable « à partir du tier T1 », avec la collecte déportée vers un service mutualisé de la flotte pour les projets « T0 ». Le système de paliers T0/T1/T2 a été retiré du framework (voir Chap 2). `analytics` est un module du catalogue comme les autres : désactivé par défaut, il s'active projet par projet, sans condition de palier.

Le module `analytics` de GitSky enregistre l'activité des visiteurs de manière **respectueuse du RGPD** et alimente le dashboard admin en visualisations de flux et d'audience. Comme tout module du catalogue, il est désactivé par défaut et s'active projet par projet via `analytics: true` dans le bloc `modules:` de `config.yaml` (clé courte, sans le préfixe `module_` — Chap 17) — ce qui devient `MODULE_ANALYTICS=true` côté `.env` généré.

## Le Middleware de Tracking

Un `TrackingMiddleware` intercepte chaque requête entrante, résout l'IP en pays/ville via **MaxMind GeoLite2** (mutualisé sur la flotte), et enregistre une entrée `Visit` en base :

```python
# app/modules/analytics/middleware.py — extrait
class TrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Enregistrement asynchrone pour ne pas ralentir la réponse
        asyncio.get_running_loop().run_in_executor(
            None, _store_visit,
            request.client.host, request.url.path, get_user_id(request)
        )
        return response
```

### Un Tracking Non-Bloquant

Il est crucial que l'enregistrement d'une visite ne ralentisse pas la réponse. L'appel à `run_in_executor` délègue l'écriture en base à un thread séparé, la réponse HTTP part immédiatement.

### Géolocalisation Anonymisée

L'IP réelle n'est jamais stockée ; seul un **hash salé** (`ip_hash`) est conservé pour identifier les visiteurs uniques sans les tracer individuellement.

```python
def _store_visit(ip: str, path: str, user_id: int | None):
    geo = geolocate(ip)   # Résolution GeoIP mutualisée
    visit = Visit(
        ip_hash=hash_ip(ip),   # SHA-256 avec sel de projet
        country_code=geo["country_code"],
        city=geo["city"],
        path=path,
        user_id=user_id,
    )
    # … persistance
```

## Le Service GeoIP Partagé

Plutôt que de maintenir une base MaxMind par projet (150 Mo par instance), la flotte GitSky partage **un unique service GeoIP** exposé sur le réseau interne du VPS. Chaque projet interroge ce service via `app/shared/clients/geoip_client.py` (voir Chap 18).

Cette mutualisation apporte trois avantages :

- Une seule base MaxMind à mettre à jour mensuellement.
- Une empreinte disque projet minimale.
- Une mise à jour du service GeoIP sans redéploiement des projets.

## Visualisations Admin

Le module apporte deux composants au dashboard admin.

### 1. Carte Mondiale (World Map)

Basée sur `react-simple-maps` et les données GeoIP agrégées, elle affiche la provenance géographique des visiteurs. Les zones sont colorées par densité.

### 2. Timeline d'Activité

Basée sur `recharts`, elle génère des graphiques temporels du nombre de visites par jour. Les données sont filtrables par rôle (`anonymous`, `user`, `premium`, `admin`) pour distinguer trafic prospect et engagement client.

```tsx
// Exemple simplifié de l'appel Analytics
const res = await fetch(`/api/admin/analytics/world?days=30`);
const data = await res.json();
// data = { countries: [{ code: "FR", visits: 1234 }, ...] }
```

## Endpoints Analytics

| Endpoint | Rôle |
|---|---|
| `GET /api/admin/analytics/world?days=N` | Agrégation par pays sur N jours |
| `GET /api/admin/analytics/timeline?days=N` | Série temporelle des visites |
| `GET /api/admin/analytics/paths?days=N` | Top des URLs consultées |

Tous les endpoints sont protégés par la dépendance `require_admin`.

## Conformité RGPD

Le module respecte trois principes qui l'exemptent de la nécessité d'un consentement cookies :

1. **Aucune donnée personnelle** stockée (pas d'IP en clair, pas d'identifiant persistant côté client).
2. **Pas de cookie de tracking** — le `ip_hash` est calculé côté serveur.
3. **Finalité limitée** — analytics purement agrégés, pas d'usage marketing ni de recoupement avec des tiers.

Cette conformité est un choix architectural : GitSky **ne peut pas** stocker d'IP en clair, même si un projet le voulait, sans réécrire le module.

## Purge et Rétention

Les entrées `Visit` sont purgées automatiquement au-delà d'un délai configurable (`ANALYTICS_RETENTION_DAYS`, 90 jours par défaut). Un cron quotidien exécute :

```sql
DELETE FROM visits WHERE created_at < now() - interval '90 days';
```

pour maintenir la table à taille raisonnable.

---

*Le tracking analytique étant traité, nous voyons dans le chapitre suivant le module `security` qui journalise les tentatives d'intrusion via un middleware complémentaire.*
