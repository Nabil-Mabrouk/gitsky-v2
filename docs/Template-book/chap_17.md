# Le Générateur `create-gitsky-project`

## Introduction

Le générateur est le composant qui transforme GitSky d'un template documenté en un template **opérationnel**. Sans lui, chaque nouveau projet exigerait un fork du repository, un renommage manuel de tous les identifiants, une réécriture de `.env`, une configuration Traefik ad hoc — soit plusieurs heures d'erreurs potentielles.

Avec le générateur, un `config.yaml` de 30 lignes suffit pour produire un projet démarrable en une commande.

Ce chapitre décrit le générateur, son fichier de configuration, son fonctionnement, et sa procédure de mise à jour des projets existants.

## Choix Technique : Copier

Le générateur est bâti sur **[Copier](https://copier.readthedocs.io/)** — un moteur de scaffolding Jinja2 avec deux propriétés critiques pour GitSky :

1. **Génération initiale** à partir d'un template et d'un fichier de réponses.
2. **Mise à jour** d'un projet déjà généré lorsque le template évolue — indispensable pour propager un correctif de sécurité à 20 projets en production.

Cookiecutter, l'alternative populaire, ne fait que la génération initiale. Elle est inadaptée dès qu'on maintient une flotte.

Installation :

```bash
pip install copier
```

## Le Fichier `config.yaml`

Chaque projet est décrit par un fichier YAML unique, versionné dans un repo central `startup-factory-configs/` :

```yaml
# projects/pain-scraper.yaml
project:
  name: pain-scraper
  domain: pain-scraper.mystudio.com

modules:
  admin: true
  agentic: true
  monetization_subscription: true

data_models:
  - name: Company
    fields:
      name: str
      url: str
      pain_signal: text
      priority: int

domain_routes:
  - prefix: /api/pains
    handlers: pains.py

branding:
  primary_color: "#4F46E5"
  primary_foreground: "#FFFFFF"
  font_family: "Inter"
  logo: assets/pain-scraper-logo.svg

fleet:
  register: true                   # inscription au fleet dashboard
  stripe_account: mystudio_main    # compte Stripe partagé
```

Les propriétés se répartissent en six catégories :

| Catégorie | Rôle |
|---|---|
| `project` | Identité du projet (nom, domaine) |
| `modules` | Sélection directe des flags module actifs (Chap 2) — aucun profil par défaut à surcharger |
| `data_models` | Modèles SQLAlchemy à scaffolder dans `app/domain/` |
| `domain_routes` | Routeurs FastAPI à scaffolder dans `app/domain/` |
| `branding` | Variables CSS et actifs à injecter dans le frontend |
| `fleet` | Enregistrement dans les services partagés de la flotte |

## Génération d'un Nouveau Projet

Une seule commande produit le projet :

```bash
copier copy \
    --data-file projects/pain-scraper.yaml \
    https://github.com/mystudio/gitsky-template \
    ~/projects/pain-scraper
```

Ce que le générateur fait, en 30 secondes :

1. **Clone le template** localement.
2. **Applique les substitutions Jinja2** dans tous les fichiers (nom du projet, flags module, branding).
3. **Scaffolde `app/domain/`** avec les modèles et routes déclarés dans `config.yaml`.
4. **Génère la migration Alembic initiale** pour le domaine et pour chaque module activé.
5. **Applique le branding** en réécrivant les variables CSS Tailwind et le logo.
6. **Génère les labels Traefik** pointant vers le domaine du projet dans le `docker-compose.yml`.
7. **Prépare la base PostgreSQL** du projet : génère des credentials aléatoires dans le `.env` ; le conteneur PostgreSQL du projet crée la base au premier démarrage (voir Chap 18 §2).
8. **Enregistre le projet** auprès du fleet dashboard via son API (voir Chap 19).
9. **Crée un commit git initial** dans le nouveau repo.

Le projet est ensuite démarrable en une commande :

```bash
cd ~/projects/pain-scraper
docker compose up -d
```

## Logique Complexe : Context Hooks, Tasks et Migrations

Contrairement à Cookiecutter, Copier n'a pas de scripts `pre_gen`/`post_gen`. Il expose **trois mécanismes distincts**, que GitSky combine :

| Mécanisme | Déclaration | Moment | Rôle dans GitSky |
|---|---|---|---|
| **Context hook** | `_jinja_extensions` + classe `ContextHook` (paquet `copier-template-extensions`) | Avant le rendu Jinja | Normalise les flags `MODULE_*` fournis par `config.yaml`, calcule les valeurs dérivées (nom de base, workers Gunicorn par défaut) — sans multiplier les questions posées |
| **`_tasks`** | Liste de commandes dans `copier.yml` | Après la génération des fichiers | Provisionne la DB, génère les migrations, enregistre au fleet dashboard, crée le dépôt GitHub et pousse le commit initial (Chap 26), initialise le repo git local |
| **`_migrations`** | Liste versionnée dans `copier.yml` | Lors d'un `copier update` | Applique les nouvelles migrations sans casser les données existantes |

Le **context hook** est l'équivalent d'un « pré-traitement » : il enrichit le contexte Jinja avant que les fichiers ne soient rendus. C'est là que les flags de modules sont normalisés, avec **exactement la même logique que le runtime** (source unique de vérité) :

```python
# extensions/context.py
from copier_template_extensions import ContextHook

class ModuleResolver(ContextHook):
    def hook(self, context: dict) -> None:
        modules = context.get("modules", {}) or {}
        context["resolved_modules"] = normalize_module_flags(modules)
```

Déclaration dans `copier.yml` :

```yaml
_jinja_extensions:
  - copier_template_extensions.TemplateExtensionLoader
  - extensions/context.py:ModuleResolver

_tasks:
  - "python .copier/tasks/provision_db.py"
  - "python .copier/tasks/register_fleet.py"
  - "git init && git add -A && git commit -m 'Initial commit'"
```

Comme les context hooks et les `_tasks` exécutent du code, `copier copy` et `copier update` exigent le drapeau **`--trust`** (`unsafe=True` via l'API Python). Ces trois mécanismes sont ce qui distingue un scaffolder statique d'un vrai générateur de projet.

## Mise à Jour d'un Projet Existant

Quand le template GitSky évolue (nouvelle version, correctif de sécurité, nouveau module), les projets existants peuvent recevoir la mise à jour :

```bash
cd ~/projects/pain-scraper
copier update
```

Copier applique un **diff à trois voies** :

- État actuel du projet.
- État du template au moment de la génération initiale.
- Nouvel état du template.

Les modifications spécifiques au projet (code métier, contenu) sont préservées. Les modifications côté template (nouveaux fichiers, correctifs) sont appliquées. Les conflits sont marqués pour résolution manuelle — Copier ne casse rien silencieusement.

**Recommandation opérationnelle :** exécuter `copier update` sur tous les projets de la flotte lors d'un correctif de sécurité critique. Le fleet dashboard (Chap 19) fournit une vue "template version" par projet pour identifier ceux qui sont à jour.

## Bootstrapping d'une Flotte : Zero-to-N Projets

Le générateur permet une procédure de démarrage d'une flotte en trois commandes :

```bash
# 1. Prépare les services partagés du VPS (une seule fois)
./scripts/bootstrap-fleet.sh

# 2. Pour chaque idée à tester, crée un YAML et génère le projet
copier copy --data-file projects/idea-1.yaml <template> ~/projects/idea-1
copier copy --data-file projects/idea-2.yaml <template> ~/projects/idea-2
# … 30 projets en 30 minutes

# 3. Démarre tous les projets
for dir in ~/projects/*/; do
    (cd "$dir" && docker compose up -d)
done
```

Le passage manuel à 30 projets serait impraticable. Le générateur rend cette échelle atteignable.

## Anti-Patterns à Éviter

- **Éditer les fichiers générés à la main sans remonter la modification dans le template.** Toute correction utile à plusieurs projets doit remonter au template pour propagation via `copier update`.
- **Sauter le fleet register.** Un projet non enregistré n'apparaît pas dans le dashboard et ne bénéficie ni du suivi de santé ni des alertes (Chap 19).
- **Cloner un projet existant plutôt que le générer.** Le clone hérite des dérives et empêche la mise à jour propre du template.

---

*Le générateur produit les projets ; les services partagés (Chap 18) leur donnent leurs points de convergence.*
