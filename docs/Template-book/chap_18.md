# Services Partagés sur un Seul VPS

## Introduction

Une flotte GitSky repose sur plusieurs **services partagés** qui vivent au niveau du VPS et sont consommés par tous les projets. Sans cette mutualisation, chaque projet dupliquerait ces composants — chaque instance porterait sa propre base MaxMind, sa propre clé API LLM, son propre relais SMTP — ce qui rendrait la flotte économiquement et opérationnellement ingérable.

Ce chapitre décrit chacun de ces services : rôle, implémentation recommandée, contrat d'interface, configuration.

## Vue d'Ensemble

```text
+--------------------------------------------------+
|         VPS mutualisé — services partagés        |
+--------------------------------------------------+
|                                                  |
|  [Traefik]         HTTPS wildcard + routing      |
|  [PostgreSQL]      données des services partagés  |
|  [Landing          Collecte des leads T0         |
|   Collector]       partagée                      |
|  [LLM Proxy]       Clés API + quotas             |
|  [GeoIP]           Résolution IP → pays/ville    |
|  [SMTP Relay]      Emails transactionnels        |
|  [Stripe Webhook   Routage des events vers       |
|   Router]          le bon projet                 |
|                                                  |
|         ↕ Consommés par tous les projets ↕       |
|                                                  |
|  Projet A (T0)  Projet B (T1)  Projet C (T2)  … |
+--------------------------------------------------+
```

Tous les services partagés vivent sur le réseau interne `shared-services-net` du VPS, jamais exposé à Internet — à une exception délibérée près : la capture du landing collector (§3), qui doit être joignable depuis chaque landing T0. Le principe reste le même : seule cette route précise passe par Traefik, jamais le service dans son ensemble.

## 1. Traefik : Routage HTTPS Mutualisé

Traefik est déjà décrit au Chap 1 comme le reverse proxy du template. Au niveau flotte, son rôle s'étend :

- Un unique certificat wildcard `*.mystudio.com` via Let's Encrypt DNS-01.
- Auto-découverte des projets qui rejoignent le réseau `proxy-net`.
- Middleware `RateLimit` par défaut (100 req/s par IP) pour tous les projets.
- Middleware `IPWhitelist` négatif alimenté par le job d'analyse des `SecurityEvent` (voir Chap 14).

```yaml
# shared-services/traefik/docker-compose.yml
services:
  traefik:
    image: traefik:v3.1
    command:
      - --providers.docker=true
      - --providers.docker.network=proxy-net
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.dnsChallenge=true
      - --certificatesresolvers.letsencrypt.acme.dnsChallenge.provider=cloudflare
    ports:
      - "80:80"
      - "443:443"
    networks:
      - proxy-net
```

## 2. PostgreSQL : un conteneur par projet

Chaque projet doté d'une base embarque **son propre conteneur PostgreSQL**,
défini dans son `docker-compose.yml` (Chap 1), plutôt qu'une base parmi d'autres
dans une instance partagée. Cette isolation par conteneur permet :

- La restauration ou le kill d'un projet sans impacter les autres — on détruit
  un conteneur et son volume, rien d'autre.
- Des sauvegardes indépendantes, un dump par conteneur (Chap 23).
- Une révocation nette : supprimer le conteneur coupe tout accès, plus
  radicalement qu'un `REVOKE`.
- **Une isolation CPU/I-O réelle** : une requête lourde ou un autovacuum emballé
  sur un projet ne dégrade pas les autres. On ne peut pas plafonner le CPU d'une
  *base* au sein d'une instance ; on le peut pour un *conteneur*.
- **Un plafond de connexions par projet** : chaque conteneur dispose de ses
  ~100 connexions, sans se disputer un pool commun.

Le prix est de ~52 Mo de RAM par conteneur PostgreSQL au repos (mesuré,
`postgres:16.3-alpine`). Sur une flotte réaliste — une dizaine de T1/T2 dotés
d'une base — cela reste sous 1 Go, largement dans le budget du VPS (voir le
tableau des coûts). **Les T0 n'ont pas de base propre** (§3) et ne coûtent rien
de ce côté.

> **Note d'architecture.** Une première version du template mutualisait une
> seule instance PostgreSQL avec une base par projet. Elle économisait ~500 Mo
> de RAM sur le VPS de 8 Go, mais au prix d'un couplage fort : une requête
> pathologique ou un autovacuum en retard sur un projet T1 non validé pouvait
> dégrader les T2 qui, eux, génèrent du revenu. Sur une *startup factory* où le
> code T0/T1 est expérimental par construction, concentrer des codebases non
> éprouvées dans la même instance que les projets rentables était le mauvais
> compromis. Le conteneur par projet a donc été retenu — les trois bénéfices
> ci-dessus (restauration, sauvegarde, révocation) y sont d'ailleurs *plus*
> vrais qu'avec une base partagée.

La création de la base est prise en charge par Compose au premier démarrage
(variables `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` du `.env`). Le
générateur produit ces credentials — un mot de passe aléatoire par projet — et
les injecte dans le `.env` :

```bash
# À la génération (create-gitsky-project) : credentials uniques par projet.
POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_hex(24))")
```

Une instance PostgreSQL partagée subsiste néanmoins dans les services partagés,
mais **uniquement pour les données des services eux-mêmes** : la table centrale
du landing collector (§3) et les logs du LLM proxy. Elle n'héberge aucune base
de projet.

## 3. Landing Collector

Pour le tier T0, chaque projet est une simple landing sans base de données propre. Les captures d'emails doivent quand même être collectées quelque part. Le **landing collector** est un service partagé unique qui reçoit les formulaires via une API commune et les persiste dans une table centrale.

```python
# shared-services/landing-collector/main.py — extrait
@app.post("/leads")
async def collect_lead(lead: LeadIn):
    async with get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO leads (project, email, source, utm_campaign, created_at) "
            "VALUES ($1, $2, $3, $4, now())",
            lead.project, lead.email, lead.source, lead.utm_campaign,
        )
    return {"ok": True}
```

Une T0 poste **en same-origin**, sur son propre domaine — pas sur un domaine dédié au collecteur (un hostname interne comme `landing-collector.mystudio.internal` ne résoudrait de toute façon nulle part publiquement, et forcerait une configuration CORS pour rien) :

```tsx
await fetch("/leads", {
    method: "POST",
    body: JSON.stringify({ project: "pain-scraper", email }),
});
```

Ce `/leads` same-origin atterrit sur Traefik comme n'importe quelle requête vers le domaine de la landing — mais Traefik le route vers le landing collector, pas vers le frontend du projet, grâce à un routeur **sans contrainte `Host()`** : `Path(\`/leads\`) && Method(\`POST\`)`. Cette règle matche sur tous les domaines de la flotte à la fois, ce qui évite de déclarer une route par projet. `Path()` est un match exact (pas `PathPrefix()`) : seule cette unique route est exposée, jamais `/leads/{project}` ni `/leads/{project}/stats` (§ci-dessous) — le collecteur reste pour le reste sur `shared-services-net`, injoignable depuis Internet.

Le fleet dashboard (Chap 19) lit cette table pour afficher le funnel de chaque projet T0, et un onglet Leads (Chap 19) permet de consulter la liste brute des emails captés. La **capture** (`POST /leads`) reste publique — les landings postent sans secret — mais la **lecture**, que ce soit les stats agrégées (`GET /leads/{project}/stats`) ou la liste (`GET /leads/{project}`), est réservée au dashboard : elle exige un en-tête `X-Collector-Token` comparé à `COLLECTOR_STATS_TOKEN`, et n'est de toute façon joignable QUE depuis `shared-services-net` (jamais via Traefik). Sinon, le funnel ou les emails de n'importe quel projet fuiteraient à quiconque joint le collecteur. Comme partout dans le châssis : ouvert en développement sans token, `503` fail-closed en production non configurée.

## 4. LLM Proxy Partagé

Décrit au Chap 15 (agentic) et au Chap 5 (clients partagés), le LLM proxy est le point de convergence de tous les appels IA de la flotte. Implémentation recommandée : **LiteLLM**.

```yaml
# shared-services/llm-proxy/config.yaml
model_list:
  - model_name: claude-sonnet-4-6
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: claude-opus-4-7
    litellm_params:
      model: anthropic/claude-opus-4-7
      api_key: os.environ/ANTHROPIC_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: postgresql://litellm:pwd@postgres/litellm_logs

litellm_settings:
  set_verbose: false
```

Chaque projet reçoit son propre token d'authentification, avec quota configurable :

```bash
# Créer un token de projet avec quota
curl -X POST https://llm-proxy.internal/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{"key_alias": "pain-scraper", "max_budget": 20.00, "budget_duration": "30d"}'
```

Les logs consolidés servent au fleet dashboard pour afficher le coût LLM par projet.

## 5. Relais SMTP

Un unique compte SMTP (par exemple **Resend**, **Postmark**, ou un serveur Postfix maison) sert tous les projets. Les emails transactionnels — activation de compte, invitation waitlist, notifications de kill, reçus Stripe — passent tous par ce relais.

Chaque projet est identifié par un expéditeur (`no-reply@pain-scraper.mystudio.com`), et le contenu est rendu depuis les templates Jinja du projet lui-même.

## 6. Service GeoIP

Un unique service qui expose la résolution IP → géolocalisation via une API interne :

```yaml
# shared-services/geoip/docker-compose.yml
services:
  geoip:
    image: mystudio/geoip-service:latest
    volumes:
      - geoip_data:/data/GeoLite2   # Base MaxMind, mise à jour mensuelle par cron
    networks:
      - shared-services-net
```

Les modules `analytics` (Chap 13) et `security` (Chap 14) des projets consomment ce service via `geoip_client.py`.

## 7. Router de Webhooks Stripe

Décrit au Chap 16, un unique endpoint public reçoit tous les webhooks Stripe de la flotte et les route vers le projet cible via la métadonnée `project_name`.

```python
# shared-services/stripe-webhook-router/main.py — extrait
@app.post("/api/shop/webhook")
async def route_webhook(request: Request):
    payload = await request.body()
    event = stripe.Webhook.construct_event(
        payload, request.headers["stripe-signature"], WEBHOOK_SECRET
    )
    project = event.data.object.metadata.get("project_name")
    if not project:
        raise HTTPException(400, "Missing project_name metadata")
    await forward_to_project(project, event)
```

## Sécurité des Services Partagés

Trois règles à respecter absolument :

1. **Aucun service partagé n'est directement exposé sur Internet** — seul Traefik voit le trafic externe.
2. **Les credentials sont stockés hors du VCS** (fichier `.secrets/` ignoré par git, ou vault type Bitwarden Secrets).
3. **Un compromis d'un projet ne compromet jamais les autres** — chaque projet a ses propres credentials LLM, SMTP, DB, et ne peut pas emprunter ceux d'un autre.

## Coût Total des Services Partagés

Sur le VPS 8 Go à 20 €/mois, les services partagés consomment :

| Service | RAM | Disque |
|---|---|---|
| Traefik | ~50 Mo | ~100 Mo |
| PostgreSQL (données des services partagés) | ~200 Mo | ~2 Go (logs LLM + leads) |
| Landing Collector | ~50 Mo | négligeable |
| LLM Proxy (LiteLLM) | ~150 Mo | ~200 Mo (logs) |
| SMTP Relay (Postfix local) | ~80 Mo | ~100 Mo |
| GeoIP Service | ~100 Mo | ~200 Mo (base MaxMind) |
| Stripe Webhook Router | ~40 Mo | négligeable |
| **Total** | **~670 Mo** | **~2,6 Go** |

Il reste donc ~7,3 Go de RAM pour les projets applicatifs. À cela s'ajoutent les
conteneurs PostgreSQL **par projet** (§2) : ~52 Mo au repos chacun (mesuré,
`postgres:16.3-alpine`), uniquement pour les T1/T2 — les T0 n'ont pas de base.
Une flotte de 10 T1 + 5 T2 ajoute ainsi ~780 Mo, laissant de quoi porter la
centaine de T0 mentionnée au Chap 2 (les T0 ne consomment que leur backend).

---

*Les services partagés donnent aux projets leurs points de convergence. Le fleet dashboard (Chap 19) donne à l'opérateur la vue unifiée qui rend l'ensemble pilotable.*
