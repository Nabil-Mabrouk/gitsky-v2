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

### Module `analytics` — Tracking Anonymisé RGPD

Le modèle `Visit` enregistre l'activité sans stocker l'IP en clair :

```python
# app/modules/analytics/models.py
class Visit(Base):
    __tablename__ = "visits"
    id = Column(Integer, primary_key=True)
    ip_hash = Column(String, index=True)
    country_code = Column(String(2), index=True)
    city = Column(String)
    path = Column(String)
    user_role = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Activation : `MODULE_ANALYTICS=true`. Pour un projet qui n'active pas ce module, la collecte se fait plutôt via le landing-collector partagé, pour mutualiser l'infrastructure GeoIP (Chap 18).

### Module `security` — Journal des Événements de Sécurité

Le modèle `SecurityEvent` enregistre chaque tentative d'intrusion détectée par le `SecurityMiddleware` :

```python
# app/modules/security/models.py
class SecurityEvent(Base):
    __tablename__ = "security_events"
    id = Column(Integer, primary_key=True)
    event_type = Column(String, index=True)   # path_scan, injection_attempt…
    severity   = Column(String, index=True)   # low, medium, high, critical
    ip_address = Column(String, index=True)
    path       = Column(String)
    user_agent = Column(String)
    details    = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Activation : `MODULE_SECURITY_MIDDLEWARE=true` — désactivé par défaut comme tout module du catalogue, à activer explicitement projet par projet.

### Module `monetization` — Boutique et Abonnements

Ce module apporte trois tables, activables via deux flags indépendants (`MODULE_MONETIZATION_SHOP`, `MODULE_MONETIZATION_SUBSCRIPTION`).

#### Produits et Achats

```python
# app/modules/monetization/models.py — extrait shop
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)
    price_cents = Column(Integer, nullable=False)  # 2900 = 29 €
    stripe_price_id = Column(String)
    file_path = Column(String)
    is_active = Column(Boolean, default=True)

class Purchase(Base):
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # nullable = achat invité
    product_id = Column(Integer, ForeignKey("products.id"))
    email = Column(String, nullable=False)
    stripe_session_id = Column(String, unique=True)
    download_token = Column(String, unique=True)
    download_count = Column(Integer, default=0)
    max_downloads = Column(Integer, default=5)
    token_expires_at = Column(DateTime(timezone=True))
    fulfilled_at = Column(DateTime(timezone=True))
```

#### Abonnements

```python
# app/modules/monetization/models.py — extrait subscription
class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    stripe_subscription_id = Column(String, unique=True)
    stripe_customer_id     = Column(String)
    status                 = Column(Enum(SubscriptionStatus))
    current_period_end     = Column(DateTime(timezone=True))
    trial_end              = Column(DateTime(timezone=True))
    cancelled_at           = Column(DateTime(timezone=True))
```

Règle métier : si `status ∈ {active, trialing}`, le rôle utilisateur devient `premium`. Dès un changement d'état (échec de paiement, annulation), le rôle est rétrogradé vers `user`. Cette logique est pilotée intégralement par les webhooks Stripe, sans intervention humaine.

## Table Récapitulative des Modèles par Couche

| Modèle | Couche | Flag d'activation | Présence |
|---|---|---|---|
| `User`, `UserRole` | core | — (toujours monté, pas de flag) | toujours présente |
| `Tutorial`, `Lesson` | module `tutorials` | `MODULE_TUTORIALS` | selon projet |
| `UserProfile` | module `onboarding` | `MODULE_ONBOARDING` | selon projet |
| `Visit` | module `analytics` | `MODULE_ANALYTICS` | selon projet (sinon via collector partagé) |
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
│   ├── analytics/
│   ├── security/
│   └── monetization/
└── alembic.ini               # Configuration multi-chaînes
```

Au démarrage du service `migrate` (voir Chap 1), un runner Python parcourt les flags `MODULE_*` activés et applique la chaîne de chaque module. Point crucial : **chaque chaîne possède sa propre table de version** (`alembic_version_core`, `alembic_version_analytics`, …). C'est ce qui leur permet de cohabiter dans la base unique du projet sans écraser mutuellement leur état — une seule table `alembic_version` partagée rendrait le multi-chaînes impossible.

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
```

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

---

*Le schéma étant posé et découpé par couche, nous allons maintenant voir comment exposer ces données via une API performante dans le chapitre suivant, en respectant la même séparation core/modules.*
