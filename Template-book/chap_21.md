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

## Serveur de Production : Gunicorn + Uvicorn

En développement, nous utilisons `uvicorn --reload`. En production, **Gunicorn** orchestre plusieurs "workers" Uvicorn. Cela permet de traiter plusieurs requêtes simultanément et de redémarrer automatiquement un worker s'il échoue.

```bash
gunicorn app.core.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Le nombre de workers `-w` est calibré par tier — 2 workers suffisent pour un T1, 4 pour un T2 sous charge normale.

## Surveillance de l'État (Healthchecks)

Pour que Traefik sache si un conteneur est réellement prêt à recevoir du trafic, une instruction `HEALTHCHECK` interroge l'endpoint `/health` toutes les 30 secondes.

## Un Seul Dockerfile pour Trois Tiers

Le template GitSky n'a pas de Dockerfile par tier — **un seul Dockerfile production** est utilisé quel que soit le tier du projet. Ce sont les flags `MODULE_*` du `.env` qui décident, à l'exécution, quels routers, modèles et migrations sont chargés.

Trois avantages :

- **Un seul artefact à builder** et à stocker dans le registre — pas de multiplication d'images.
- **Passer de T1 à T2** se fait via un simple redéploiement avec un `.env` mis à jour, sans rebuild.
- **La revue de sécurité** se fait sur une seule image, pas trois.

L'empreinte disque de l'image reste identique (~200 Mo pour le backend, ~30 Mo pour le frontend). L'empreinte **mémoire** au runtime, en revanche, varie fortement selon les modules activés — c'est cette variation qui permet de porter 100 T0 sur le même VPS.

## Empreinte Mémoire par Tier (Mesurée)

| Tier | Modules activés | RAM initiale | RAM sous charge légère |
|---|---|---|---|
| T0 | landing-collector uniquement | ~50 Mo | ~60 Mo |
| T1 | Auth + security + analytics | ~180 Mo | ~250 Mo |
| T2 | Tous les modules + agentic | ~700 Mo | ~900 Mo à 1 Go |

Un T2 avec agentic actif consomme davantage que la somme des modules — le framework agentic charge des modèles et des tool registries qui ont leur propre empreinte.

---

*Le pattern Docker prod est posé pour tous les tiers. Le prochain chapitre décrit la configuration du serveur Ubuntu 24.04 qui accueille l'ensemble de la flotte, du hardening SSH au bootstrap des services partagés.*
