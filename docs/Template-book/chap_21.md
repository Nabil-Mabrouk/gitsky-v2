# Dockerisation Avancée pour la Production

## Introduction

Le passage du développement à la production nécessite une approche différente de Docker. En local nous privilégions le confort (rechargement à chaud, ports exposés) ; en production nous visons performance, sécurité et légèreté. Ce chapitre décortique les Dockerfiles optimisés du template GitSky, valides pour les trois tiers T0, T1 et T2.

## Le Pattern Multi-Stage

Le "Multi-Stage build" est la technique de référence pour créer des images de production. Elle consiste à utiliser une image pour compiler ou construire l'application, puis à copier uniquement le résultat final dans une image de base très légère.

### Backend (FastAPI)

L'image finale de GitSky ne contient pas les outils de compilation Python, seulement les dépendances installées et le code source.

*   **Stage 1 (Builder) :** installation des dépendances via `pip install --user`.
*   **Stage 2 (Production) :** récupération uniquement du dossier `.local` et du code de l'application.

### Frontend (React/Vite)

Pour React, le gain est encore plus impressionnant :

*   **Stages 1 & 2 :** installation des modules npm et exécution de `npm run build`.
*   **Stage 3 (Production) :** copie uniquement du dossier `dist` (quelques Mo de JS/CSS statique) et utilisation d'un serveur léger comme `serve` pour le mettre à disposition.

## Sécurité des Conteneurs

Une règle d'or en production : **ne jamais lancer de conteneur en tant qu'utilisateur root.**

Dans nos Dockerfiles, nous créons systématiquement un utilisateur système (`appuser`) aux droits restreints. Si un attaquant parvient à exploiter une faille dans l'application, il est confiné dans le conteneur sans pouvoir impacter l'hôte.

```dockerfile
# Exemple dans le Dockerfile
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser
```

**Le code reste en lecture seule pour `appuser`.** Le dossier `/app` appartient
à `root` : `appuser` peut l'exécuter mais pas le réécrire — une faille
applicative ne peut donc pas modifier le code en place. Attention au piège :
`WORKDIR /app` crée le dossier en `root`, et `COPY --chown=appuser` ne change que
les *fichiers copiés*, pas le dossier lui-même. Les écritures runtime légitimes
(SQLite d'un T0, uploads) vont donc dans un dossier `/data` dédié, seul
emplacement rendu inscriptible pour `appuser` :

```dockerfile
RUN mkdir -p /data && chown appuser:appuser /data
VOLUME /data
```

## Serveur de Production : Gunicorn + Uvicorn

En développement, nous utilisons `uvicorn --reload`. En production, **Gunicorn** orchestre plusieurs "workers" Uvicorn. Cela permet de traiter plusieurs requêtes simultanément et de redémarrer automatiquement un worker s'il échoue.

```bash
gunicorn app.core.main:app -k uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000
```

⚠️ **Classe de worker.** On utilise le paquet `uvicorn-worker`
(`uvicorn_worker.UvicornWorker`), et non l'ancien `uvicorn.workers.UvicornWorker`
intégré à Uvicorn : ce dernier est **déprécié depuis Uvicorn 0.30** et émet un
avertissement au démarrage.

**Le nombre de workers ne figure pas dans le `CMD`.** Le figer au build
produirait *une image par configuration*, en contradiction avec la règle « un
seul Dockerfile » ci-dessous. On passe donc le nombre par la variable
`WEB_CONCURRENCY`, que Gunicorn lit nativement, injectée depuis le `.env` du
projet — une simple valeur de configuration par projet, réglée à la création
(défaut raisonnable : 2) et ajustable à tout moment sans rebuild, par exemple
si la charge d'un projet augmente.

## Surveillance de l'État (Healthchecks)

Pour que Traefik sache si un conteneur est réellement prêt à recevoir du trafic, une instruction `HEALTHCHECK` interroge l'endpoint `/health` toutes les 30 secondes. On sonde avec **Python** (`urllib.request`, déjà présent dans l'image) plutôt qu'avec `curl` : cela évite une couche `apt-get` supplémentaire, allège l'image, et supprime une dépendance réseau au build. `urlopen` lève sur un `503` — le conteneur est alors marqué non sain, ce qui est exactement le comportement voulu quand la base est injoignable (Chap 23 §4.1).

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]
```

## Un Seul Dockerfile pour Tous les Projets

Le template GitSky n'a pas de Dockerfile par configuration — **un seul Dockerfile production** est utilisé quels que soient les modules activés par le projet. Ce sont les flags `MODULE_*` du `.env` qui décident, à l'exécution, quels routers, modèles et migrations sont chargés.

Trois avantages :

- **Un seul artefact à builder** et à stocker dans le registre — pas de multiplication d'images.
- **Activer un module supplémentaire** se fait via un simple redéploiement avec un `.env` mis à jour, sans rebuild.
- **La revue de sécurité** se fait sur une seule image, pas plusieurs.

L'empreinte disque de l'image reste identique quels que soient les modules activés — **~320 Mo pour le backend, ~260 Mo pour le frontend** (tailles mesurées). Le backend part de `python:3.12-slim` (~180 Mo) plus les dépendances installées ; le frontend de `node:24-alpine` (~230 Mo) plus `serve` et le `dist/` (le bundle statique lui-même ne pèse que quelques centaines de Ko, mais l'image qui le sert porte la base Node). L'empreinte **mémoire** au runtime, en revanche, varie fortement selon les modules activés — c'est cette variation qui permet de porter des dizaines de projets légers sur le même VPS aux côtés de quelques projets complets (Chap 2).

## Empreinte Mémoire par Combinaison de Modules (Mesurée)

| Combinaison | Modules activés | RAM initiale | RAM sous charge légère |
|---|---|---|---|
| Landing seule | Core (auth + SEO) uniquement | ~50 Mo | ~60 Mo |
| App avec compte utilisateur | Core + admin + security + analytics | ~180 Mo | ~250 Mo |
| SaaS complet | Tous les modules + agentic | ~700 Mo | ~900 Mo à 1 Go |

Un projet avec l'agentic actif consomme davantage que la somme des autres modules — le framework agentic charge des modèles et des tool registries qui ont leur propre empreinte.

---

*Le pattern Docker prod est posé pour tous les projets, quels que soient leurs modules. Le prochain chapitre décrit la configuration du serveur Ubuntu 24.04 qui accueille l'ensemble de la flotte, du hardening SSH au bootstrap des services partagés.*
