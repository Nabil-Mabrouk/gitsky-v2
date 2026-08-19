# 9001-Formations

Ce dépôt réunit **deux projets** liés :

| Dossier | Contenu |
|---------|---------|
| [`docs/formation-claude-code/`](docs/formation-claude-code/) | Un **cursus de formation** (français) à l'usage professionnel de Claude Code : 9 modules + évaluation finale. 100 % Markdown, aucun code. Voir son [README](docs/formation-claude-code/README.md). |
| [`docs/Template-book/`](docs/Template-book/) + [`src/`](src/) | **GitSky** : le livre d'une *startup-factory* (`docs/Template-book/`) et son implémentation de référence (`src/`) — un générateur de projets web (FastAPI + React) tiérisés T0/T1/T2. |

Le reste de ce README concerne **GitSky** (le code).

## Ce qu'est GitSky

Un **générateur** ([Copier](https://copier.readthedocs.io/)) qui produit, à partir d'une config, un projet web complet et déployable : backend **FastAPI** (async SQLAlchemy + Alembic), frontend **React/Vite**, modules optionnels activés par *tier* (auth, analytics, sécurité, tutorials, monétisation…), et le nécessaire Docker (dev + prod). Le **livre est la source de vérité** ; le code le suit chapitre par chapitre.

```
src/
├── generator/          Le générateur Copier — SUBMODULE git (voir plus bas)
│   └── template/       L'arborescence d'un projet généré (app/, frontend/, Docker…)
├── shared_services/    Services mutualisés de la flotte (collector, studio, crontab…)
└── tests/              Suite de tests Python (pytest) du générateur et du châssis
```

`src/generator/` est un **submodule git**, dans son propre dépôt
(`gitsky-template`) — nécessaire pour que `copier.yml` vive à la racine d'un
dépôt git et que `copier update` puisse suivre les versions (Chap 17/25). Un
clone simple laisse ce dossier **vide** :

```bash
git clone --recurse-submodules <url-de-ce-depot>
# ou, après un clone déjà fait sans l'option :
git submodule update --init
```

## Prérequis

- **Python 3.12+**
- **Node.js 20+** (24 LTS recommandé) et **npm**
- **Docker** + **Docker Compose v2** (pour lancer un projet généré en local)

## Installation (environnement de dev)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r src/generator/requirements.txt \
            -r src/generator/template/requirements.txt
```

## Lancer les tests

**Backend / générateur (pytest)** — depuis la racine du dépôt :

```bash
python -m pytest src/tests
```

**Frontend (Vitest)** :

```bash
cd src/generator/template/frontend
npm install
npm test
```

## Générer un projet

```bash
python -c "from copier import run_copy; \
run_copy('src/generator', 'out/mon-projet', \
         data={'project': {'name': 'mon-projet', 'tier': 't1'}}, \
         defaults=True, unsafe=True)"
```

`tier` vaut `t0` (landing simple), `t1` (app avec auth/analytics/sécurité) ou `t2`
(catalogue complet de modules). Voir `src/generator/copier.yml` pour toutes les
options (branding, modèles métier, landing…).

## Lancer un projet généré en local

Chaque projet généré embarque un **`docker-compose.dev.yml`** pensé pour tourner
en une commande, sans Traefik, sans domaine, sans PostgreSQL (base SQLite locale,
hot-reload backend + frontend) :

```bash
cd out/mon-projet
docker compose -f docker-compose.dev.yml up --build
```

- API : http://localhost:8000 — santé sur http://localhost:8000/health
- Frontend : http://localhost:5173

Le `docker-compose.yml` (sans suffixe) est le déploiement **production** : images
buildées, réseau `proxy-net`, TLS Let's Encrypt — il n'est pas destiné au poste
local. Voir `docs/Template-book/` (Chap. 21–23) pour le déploiement.

## Conventions de contribution

- Tout le code GitSky vit sous `src/`.
- **Chaque changement est accompagné d'un test** et validé en le lançant.
- On ne contourne pas un test qui échoue en l'affaiblissant : on corrige le code.
- Le **livre (`docs/Template-book/`) fait foi** : si le code diverge du plan, on
  s'arrête et on tranche avant de modifier le livre.
