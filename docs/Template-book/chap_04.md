# Modélisation des Données avec SQLAlchemy

## Introduction à la Modélisation

Le schéma de données de GitSky est réparti entre le **core** (présent dans tous les projets) et les **modules** (chacun apportant ses propres tables, activées uniquement si le module l'est). Cette organisation reflète directement l'architecture décrite au chapitre précédent : chaque table appartient à une couche identifiée, et un module désactivé n'introduit ni ses modèles ni ses migrations dans la base.

Nous utilisons **SQLAlchemy** comme ORM, ce qui nous permet de :

1. Bénéficier d'une validation de type forte via Python.
2. Manipuler des objets Python plutôt que d'écrire du SQL brut.
3. Garantir l'intégrité référentielle entre entités.

## Les Modèles du Core

Deux entités sont toujours présentes, dans tout projet GitSky : l'authentification est une capacité **core**, câblée directement — jamais un flag `MODULE_*` optionnel (voir Chap 2).

### `User` — L'Identité et les Rôles

Le modèle `User` centralise l'identité et les permissions. Une énumération `UserRole` hiérarchise les accès :

```python
# app/core/models.py
class UserRole(str, enum.Enum):
    anonymous = "anonymous"
    waitlist  = "waitlist"
    user      = "user"
    premium   = "premium"
    admin     = "admin"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Même un projet landing pur (aucun module optionnel activé) garde la table `users` — elle appartient au core, toujours monté et toujours migré, quels que soient les modules choisis. En pratique, un tel projet ne s'en sert souvent que pour les comptes opérateur : les emails de leads captés sur la landing passent par le landing-collector partagé plutôt que par un compte utilisateur dédié (voir Chap 18).

## Les Modèles des Modules

Chaque module apporte ses propres modèles, activés uniquement si le flag `MODULE_*` correspondant est à `true`.

### Module `tutorials` — Contenu Pédagogique

Ce module implémente une université virtuelle. Il repose sur une relation **One-to-Many** entre `Tutorial` et `Lesson` :

```python
# app/modules/tutorials/models.py
class Tutorial(Base):
    __tablename__ = "tutorials"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)
    lang = Column(String(5), default="fr", index=True)
    access_role = Column(Enum(UserRole), default=UserRole.user)

    lessons = relationship("Lesson", back_populates="tutorial", order_by="Lesson.order")

class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True)
    tutorial_id = Column(Integer, ForeignKey("tutorials.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    content = Column(Text)   # Markdown
    order = Column(Integer, default=0)
```

Activation : `MODULE_TUTORIALS=true`.

### Module `onboarding` — Profilage Dynamique

Le modèle `UserProfile` stocke les résultats d'un questionnaire d'onboarding, en relation 1:1 avec `User` :

```python
# app/modules/onboarding/models.py
class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    flow_id = Column(String, nullable=False)
    answers = Column(Text)   # JSON sérialisé
    profile = Column(String) # Label calculé (ex: 'power_user')
    score = Column(Integer)
```

Activation : `MODULE_ONBOARDING=true`.

### Ancien module `analytics` — retiré

Le modèle `Visit` (table `visits`) du module `analytics` a été retiré avec le module le 27 novembre 2026 : la mesure d'audience passe par Umami (Chap 13). La migration core `0005` supprime `visits` et `alembic_version_analytics` des bases déjà déployées, seulement si cette table de version existe.

---|---|---|---|
| `User`, `UserRole` | core | — (toujours monté, pas de flag) | toujours présente |
| `Tutorial`, `Lesson` | module `tutorials` | `MODULE_TUTORIALS` | selon projet |
| `UserProfile` | module `onboarding` | `MODULE_ONBOARDING` | selon projet |
| `SecurityEvent` | module `security` | `MODULE_SECURITY_MIDDLEWARE` | selon projet |
| `Product`, `Purchase` | module `monetization` | `MODULE_MONETIZATION_SHOP` | selon projet |
| `Subscription` | module `monetization` | `MODULE_MONETIZATION_SUBSCRIPTION` | selon projet |

## Gestion des Migrations avec Alembic

Le schéma évolue par ajouts versionnés. Chaque couche a **sa propre chaîne de migrations** :

```text
backend/alembic/
├── core/                     # Migrations du core (User, Role)
│   ├── env.py
│   └── versions/
├── modules/
│   ├── tutorials/            # Migrations du module tutorials
│   ├── onboarding/
│   ├── security/
│   └── monetization/
├── domain/                   # Migrations métier du projet (app/domain/)
│   ├── env.py
│   └── versions/
└── alembic.ini               # Configuration multi-chaînes
```

Au démarrage du service `migrate` (voir Chap 1), un runner Python parcourt les flags `MODULE_*` activés et applique la chaîne de chaque module. Point crucial : **chaque chaîne possède sa propre table de version** (`alembic_version_core`, `alembic_version_tutorials`, …). C'est ce qui leur permet de cohabiter dans la base unique du projet sans écraser mutuellement leur état — une seule table `alembic_version` partagée rendrait le multi-chaînes impossible.

```python
# scripts/migrate.py — extrait
# _config(section, dossier, version_table, url) construit un alembic.config.Config.
from alembic import command
from app.core.config import get_settings

def run_migrations() -> None:
    settings = get_settings()
    url = settings.database_url

    # Core : toujours appliqué.
    command.upgrade(_config("alembic", "alembic/core", "alembic_version_core", url), "head")

    # Modules : une chaîne (et une table de version) par flag MODULE_* activé.
    if settings.module_tutorials:
        command.upgrade(_config("tutorials", "alembic/modules/tutorials", "alembic_version_tutorials", url), "head")
    if settings.module_onboarding:
        command.upgrade(_config("onboarding", "alembic/modules/onboarding", "alembic_version_onboarding", url), "head")
    # … idem pour les autres modules

    # Métier (app/domain/) : toujours, et en dernier.
    command.upgrade(_config("domain", "alembic/domain", settings.domain_version_table, url), "head")
```

> **Écart assumé : la chaîne `domain`.** Dans la conception initiale, seules les couches core et modules avaient une chaîne. Les modèles métier du projet (`app/domain/models.py`) n'en avaient aucune : ils n'étaient créés que par le `create_all` du démarrage en développement, et donc **jamais en production**. Ce bug a été trouvé sur le projet 0-hl. Avant cette correction, politique-ia, f-ynd et ai-qube avaient chacun ajouté leur propre chaîne à la main, avec des variantes divergentes. Le châssis fournit désormais `alembic/domain/` (vide à la génération, une chaîne vide n'a aucun effet) et une section `[domain]` dans `alembic.ini`. Le runner l'applique selon trois règles :
>
> - **Toujours**, parce que `app/domain/` n'est pas un module optionnel.
> - **En dernier**, parce que les tables métier peuvent référencer `users` ou les tables des modules.
> - **Avec une table de version réglable** : `DOMAIN_VERSION_TABLE`, par défaut `alembic_version_domain`. Elle permet de reprendre une chaîne déjà nommée autrement, comme `alembic_version_fynd` pour f-ynd. Sans ce réglage, ces migrations seraient rejouées sur des tables qui existent déjà.
>
> Le `env.py` de cette chaîne filtre aussi les tables de la base que les modèles métier ne déclarent pas. Sans ce filtre, `--autogenerate` comparerait les modèles métier à la base réelle et proposerait de **supprimer** `users` et toutes les tables des modules.

Un runner Python (plutôt qu'un script shell) reste portable entre environnements et s'appelle directement dans les tests. La CLI Alembic classique (`alembic --name onboarding upgrade head`) demeure disponible grâce aux sections déclarées dans `alembic.ini`.

Cette approche implique un coût de complexité initial, mais permet trois propriétés critiques :

1. **Une base de données minimale par projet** — pas de tables inutiles, seulement celles des modules réellement activés (plus le core, toujours présent).
2. **Activer un module en cours de vie du projet = ajouter sa chaîne de migrations** sans risque sur celles déjà appliquées.
3. **Désactiver un module** n'a pas d'impact sur les autres, ni sur le core.

### Workflow Alembic pour un Nouveau Module

Lors de la création d'un nouveau module :

1. **Créer le dossier** : `alembic/modules/mon_module/`.
2. **Générer une migration** : `alembic --name mon_module revision --autogenerate -m "initial"`.
3. **Vérifier le script généré** avant application.
4. **Ajouter le flag** correspondant à `Settings`, une section dans `alembic.ini`, et l'appliquer dans le runner `scripts/migrate.py`.

### Workflow Alembic pour les Modèles Métier

La chaîne `domain` existe déjà : il n'y a ni dossier, ni flag, ni section à créer.

1. **Modifier** `app/domain/models.py`.
2. **Générer une migration** à partir d'une base à jour : `alembic -n domain revision --autogenerate -m "..."`.
3. **Vérifier le script généré** avant application, en particulier que `upgrade()` ne supprime rien d'inattendu.
4. **Pousser** : le service `migrate` l'applique au déploiement.

---

*Le schéma étant posé et découpé par couche, nous allons maintenant voir comment exposer ces données via une API performante dans le chapitre suivant, en respectant la même séparation core/modules.*
