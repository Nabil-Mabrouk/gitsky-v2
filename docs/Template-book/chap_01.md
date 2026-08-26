# Architecture Conteneurisée Professionnelle

## Philosophie de l'Architecture
Une architecture conteneurisée professionnelle repose sur quatre principes fondamentaux pour garantir la fiabilité, la scalabilité et la multi-tenance du template **GitSky**.

**Parité des environnements :** Le code qui tourne en développement sur votre machine doit être structurellement identique à celui qui tourne en production sur le serveur. Seules les configurations (secrets, URLs, niveaux de logs) changent.

**Isolation et Segmentation :** Chaque service est confiné dans son propre conteneur. Le frontend ne communique jamais directement avec la base de données ; tout passe par l'API Backend. Cette segmentation limite les risques de sécurité.

**Infrastructure-as-Code :** Toute notre infrastructure est décrite dans des fichiers YAML versionnés. Recréer l'intégralité d'un projet GitSky ne nécessite qu'une seule commande.

**Multi-tenance native :** Un même VPS doit pouvoir héberger simultanément des dizaines de projets isolés. Cela impose que le nom du projet (`PROJECT_NAME`) paramètre l'ensemble des ressources (conteneurs, réseaux, base de données), et que les composants partagés — Traefik en premier lieu — le soient explicitement.

## Vue d'Ensemble des Services

Le projet GitSky est composé de trois briques majeures orchestrées par Docker :

```text
+--------------------------------------------------+
|                  ACCÈS PUBLIC                    |
|      Utilisateur --> Port 80/443 --> [Traefik]   |
+------------------------+-------------------------+
                         |
          +--------------v--------------+
          |          proxy-net          |
          |  [Traefik] -> [Frontend:5173]|
          |  [Traefik] -> [Backend:8000] |
          +-------+-----------+---------+
                  |           |
     +------------v-----------v------------+
     |           internal-net              |
     |  (Réseau privé et isolé)            |
     |                                     |
     |  [Backend] <------> [PostgreSQL]    |
     |  [Migrate] <------> [PostgreSQL]    |
     +-------------------------------------+
```

**Les services clés :**

- **Frontend (React/Vite) :** L'interface utilisateur moderne et réactive.
- **Backend (FastAPI) :** Le cerveau traitant la logique métier et l'accès aux données.
- **Database (PostgreSQL) :** Le stockage persistant et robuste.
- **Migrate (Alembic) :** Un service éphémère qui met à jour le schéma de la base de données au démarrage.

## Orchestration avec Docker Compose

L'orchestration est gérée par trois fichiers distincts pour séparer la structure de la configuration d'environnement.

### 1. La Base Commune : `docker-compose.yml`

Ce fichier définit la "squelette" de notre application sans valeurs en dur.

```yaml
services:
  frontend:
    container_name: ${PROJECT_NAME}_frontend
    environment:
      - VITE_API_URL=${VITE_API_URL}
    networks:
      - proxy-net
      - internal-net
    depends_on:
      - backend

  backend:
    container_name: ${PROJECT_NAME}_backend
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      - ENVIRONMENT=${ENVIRONMENT}
      - SECRET_KEY=${SECRET_KEY}
    networks:
      - proxy-net
      - internal-net
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16.3-alpine
    container_name: ${PROJECT_NAME}_db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    volumes:
      - db_data:/var/lib/postgresql/data
    networks:
      - internal-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5

  migrate:
    container_name: ${PROJECT_NAME}_migrate
    command: python -m scripts.migrate   # applique core + chaînes des modules activés
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    networks:
      - internal-net
    depends_on:
      db:
        condition: service_healthy
    restart: "no"

volumes:
  db_data:

networks:
  proxy-net:
    external: true
    name: proxy-net
  internal-net:
    driver: bridge
    internal: true
```

### 2. L'environnement de Développement : `docker-compose.dev.yml`

En développement, nous activons le rechargement automatique (hot-reload) et exposons les ports pour faciliter le débuggage.

```yaml
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    volumes:
      - ./frontend:/app
      - /app/node_modules
    ports:
      - "5173:5173"

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    volumes:
      - ./backend:/app
      - ./backend/uploads:/app/uploads
    ports:
      - "8000:8000"

  db:
    ports:
      - "5432:5432" # Permet d'utiliser DBeaver ou TablePlus localement
```

## Gestion des Variables d'Environnement

Un projet professionnel ne doit jamais contenir de secrets (mots de passe, clés API) dans le code source. Nous utilisons un fichier `.env` (ignoré par Git) basé sur un modèle `.env.example`.

**Le fichier `.env.example` type pour GitSky :**

```bash
PROJECT_NAME=gitsky
ENVIRONMENT=development
VITE_API_URL=http://localhost:8000
SECRET_KEY=votre_cle_secrete_tres_longue

# PostgreSQL
POSTGRES_USER=hitl_user
POSTGRES_PASSWORD=hitl_password
POSTGRES_DB=hitl_db
```

## Reverse Proxy et SSL avec Traefik

Pour la production, nous utilisons **Traefik**. C'est un reverse proxy moderne qui gère automatiquement les certificats SSL (HTTPS) via Let's Encrypt. 

L'architecture GitSky prévoit que Traefik tourne dans un conteneur séparé, partageant le réseau `proxy-net`. Chaque service (Frontend et Backend) s'annonce à Traefik via des **labels** Docker :

```yaml
# Exemple de labels pour le Backend en production
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.backend-gitsky.rule=Host(`api.votre-domaine.com`)"
  - "traefik.http.routers.backend-gitsky.entrypoints=websecure"
  - "traefik.http.routers.backend-gitsky.tls.certresolver=letsencrypt"
```

## Hébergement Multi-Projets sur un Seul VPS

Le template GitSky est conçu pour cohabiter à plusieurs dizaines d'instances sur un unique VPS. Trois mécanismes rendent cela viable.

### Un Seul Traefik pour Toute la Flotte

Un unique conteneur Traefik tourne à l'échelle du VPS et route le trafic vers l'ensemble des projets hébergés. Chaque projet expose ses labels Traefik et rejoint le réseau `proxy-net` **partagé entre tous les projets** — Traefik les découvre automatiquement à leur démarrage.

### Certificats SSL Wildcard

Traefik gère un certificat wildcard `*.mystudio.com` via Let's Encrypt DNS-01. Ajouter un nouveau sous-domaine à un projet ne déclenche donc aucune renégociation de certificat. Le domaine premier (`mystudio.com`) est réservé au fleet dashboard qui pilote la flotte (voir Chap 19).

### Isolation Stricte par Projet

Chaque projet dispose :

- de son propre réseau `internal-net` (jamais partagé avec un autre projet)
- de sa propre base de données PostgreSQL (isolation nette, restauration ou archivage facile)
- de ses propres conteneurs backend et frontend
- d'un `PROJECT_NAME` unique qui préfixe l'ensemble des ressources Docker

```text
+--------------------------------------------------+
|              VPS mutualisé (8 Go RAM)            |
+--------------------------------------------------+
|                                                  |
|  [Traefik partagé] — wildcard *.mystudio.com     |
|         |                                        |
|    +----+-----+----------+------------+          |
|    |          |          |            |          |
|  Projet A   Projet B   Projet C  Fleet Dashboard |
|              (mystudio.com)                      |
|                                                  |
|  Chaque projet = 1 container backend             |
|                + 1 container frontend            |
|                + 1 base PostgreSQL isolée        |
|                (modules activés au choix,        |
|                 voir Chap 2)                     |
|                                                  |
+--------------------------------------------------+
```

Sur un VPS à 20 €/mois, ce modèle permet d'héberger simultanément **plusieurs dizaines de projets légers** (peu de modules actifs) ou **un nombre plus restreint de projets complets** (catalogue de modules activé en grande partie), ou un mélange des deux — voir Chap 2 pour le détail du catalogue de modules et des ordres de grandeur d'empreinte mémoire.

## Commandes de Référence

Voici les commandes essentielles pour piloter votre infrastructure :

| Action | Commande |
|---|---|
| Lancer en développement | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up` |
| Reconstruire les images | `docker compose build --no-cache` |
| Voir les logs en temps réel | `docker compose logs -f` |
| Arrêter et supprimer les conteneurs | `docker compose down` |

---

*Ce chapitre pose les fondations techniques mutualisées du template. Dans le prochain chapitre, nous détaillons le catalogue de modules qui permet à un même code base de porter aussi bien une landing minimale qu'une webapp complète, sans jamais réécrire l'architecture.*
