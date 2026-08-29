# Le Catalogue de Modules de GitSky

## Introduction

GitSky n'est pas destiné à un projet unique. Il est conçu comme un **template industriel** capable de porter un grand nombre de projets indépendants — chacun avec son propre périmètre fonctionnel, son propre domaine, son propre cycle de vie — sur une infrastructure mutualisée. Un template mono-taille échoue toujours d'un côté ou de l'autre — surdimensionné pour un projet simple, sous-dimensionné pour un produit qui a besoin d'admin, de facturation ou d'internationalisation.

La solution retenue est un **catalogue de modules à plat**, activables indépendamment via des variables d'environnement `MODULE_*`. Un même code base, un nombre arbitraire de combinaisons possibles. Chaque projet choisit à sa création exactement les modules dont il a besoin — ni plus, ni moins — et peut en activer ou désactiver d'autres à tout moment de sa vie, sans migration de « palier » ni notion de promotion.

> **Écart au livre (Phase 6)** — les versions précédentes de cet ouvrage décrivaient un système à trois paliers (T0/T1/T2) avec promotion automatique sur signal mesurable et kill mechanism en cas d'échec. Ce système a été retiré : GitSky ne présume plus qu'un projet est une idée en test destinée à grandir ou à être arrêtée — c'est un hébergement mutualisé pour des projets qui vivent leur propre trajectoire, décidée par un opérateur humain, pas par un cron. Le cycle de vie (création → actif → archivage manuel) est couvert au Chap 20.

## 1. Pourquoi un Catalogue Plutôt que des Paliers

Générer un projet coûte peu ; le faire tourner en production coûte du temps opérateur (surveillance, sauvegardes, sécurité) proportionnel à ce qu'il expose réellement. Un projet qui n'a besoin que d'une landing page et d'un formulaire de contact n'a aucune raison de charger un shell d'administration, un moteur d'onboarding ou une intégration Stripe — chaque module actif est une route de plus à sécuriser, une migration de plus à maintenir, une dépendance de plus à surveiller.

Le catalogue à plat réconcilie deux exigences :

- **Un socle minimal** commun à tout projet — authentification et SEO — présent partout, jamais à activer ni à désactiver.
- **Des modules optionnels**, chacun résolvant un besoin précis (admin, i18n, analytics, monétisation, contenu, agentic…), activables un par un selon ce que le projet fait réellement.

## 2. Le Socle Commun (Core)

Deux capacités sont présentes dans **tout** projet GitSky, sans variable d'activation :

| Capacité | Pourquoi elle est core |
|---|---|
| **Authentification** (JWT + refresh) | Un projet mutualisé sur une flotte a presque toujours besoin de comptes, ne serait-ce que pour l'accès opérateur — en faire un flag optionnel n'économisait qu'un cas rare tout en compliquant chaque autre module qui en dépend (admin, onboarding, monétisation…). |
| **SEO dynamique** | Sitemap, robots.txt et métadonnées structurées ont un coût quasi nul et un bénéfice immédiat dès la mise en ligne, quel que soit le projet. |

Comme le `landing`/`domain` métier de chaque projet, ces deux capacités ne figurent pas dans `MODULE_FLAGS` (Chap 3 §config.py) — elles sont câblées directement dans le core.

## 3. Le Catalogue des Modules Optionnels

Chaque module est un booléen indépendant, **désactivé par défaut**. Un module désactivé ne charge aucune route, aucun modèle SQL, aucune migration Alembic — l'empreinte d'un projet minimal reste faible, non pas parce que le code manque, mais parce que le code inutile est court-circuité au démarrage (Chap 3 §Modules Conditionnels).

| Module | Variable | Ce qu'il apporte | Chapitre |
|---|---|---|---|
| Admin shell | `MODULE_ADMIN` | Interface d'administration (gestion utilisateurs, contenu) | Chap 9 |
| Internationalisation | `MODULE_I18N` | Traductions FR/EN, routage par préfixe de langue | Chap 8 |
| Analytics | `MODULE_ANALYTICS` | Suivi visiteurs RGPD-compatible, dashboard de flux/audience | Chap 13 |
| Onboarding dynamique | `MODULE_ONBOARDING` | Flow de qualification/profilage configurable en JSON | Chap 12 |
| Content system | `MODULE_TUTORIALS` | Catalogue de tutoriaux/leçons (cas d'usage : université virtuelle) | Chap 11 |
| SecurityMiddleware | `MODULE_SECURITY_MIDDLEWARE` | Inspection des requêtes, journalisation `SecurityEvent` | Chap 14 |
| Framework agentic IA | `MODULE_AGENTIC` | Orchestration de services IA, crédits, recovery | Chap 15 |
| Monétisation boutique | `MODULE_MONETIZATION_SHOP` | Produits/achats ponctuels via Stripe | Chap 16 |
| Monétisation abonnements | `MODULE_MONETIZATION_SUBSCRIPTION` | Abonnements récurrents via Stripe | Chap 16 |
| Fleet (réservé au dashboard) | `MODULE_FLEET` | Registre de projets, cycle de vie, intégration GitHub — n'a de sens que pour l'app fleet dashboard elle-même, jamais pour un projet métier | Chap 19, 20, 26 |

Aucun de ces modules n'est un prérequis d'un autre, à une exception near : certains (onboarding, monétisation abonnement) supposent des comptes utilisateurs — ils s'appuient donc sur l'authentification core, déjà toujours présente.

Le fichier `.env` d'un projet minimal (landing + capture de leads, rien d'autre) :

```env
PROJECT_NAME=pain-scraper
VITE_API_URL=https://pain-scraper.mystudio.com
# Aucun MODULE_* activé : authentification et SEO restent présents (core),
# le reste est désactivé par défaut.
```

Un projet avec admin, i18n et monétisation par abonnement :

```env
PROJECT_NAME=code-reviewer-pro
MODULE_ADMIN=true
MODULE_I18N=true
MODULE_MONETIZATION_SUBSCRIPTION=true
STRIPE_SECRET_KEY=sk_live_xxx
```

Un projet qui active le framework agentic :

```env
PROJECT_NAME=code-reviewer-pro
MODULE_AGENTIC=true
ANTHROPIC_API_KEY=sk-ant-xxx
```

## 4. Base de Données : Toujours PostgreSQL, Toujours Dédiée

Chaque projet reçoit **systématiquement** son propre conteneur PostgreSQL, quel que soit son catalogue de modules activés (Chap 18 §2 détaille l'isolation par conteneur). Il n'existe plus d'exception « projet sans base » : même une simple landing avec capture de leads gagne à avoir sa propre base dès le départ — la complexité d'ajouter Postgres après coup (migration de données, changement d'infra) dépassait largement l'économie qu'elle permettait.

## 5. Empreinte : Fonction des Modules, Pas d'un Palier

L'empreinte mémoire d'un projet dépend directement du nombre de modules activés, pas d'une case dans laquelle il serait rangé. Un projet réduit au socle core (auth + SEO, rien d'autre) mesure une empreinte proche du plancher observé pour le châssis ; chaque module optionnel activé ajoute son propre delta — le framework agentic, en particulier, charge des modèles et des registries d'outils qui pèsent nettement plus lourd que les autres modules (détail chiffré au Chap 21 §Empreinte Mémoire).

Cette variabilité, plutôt qu'un coût fixe par palier, est ce qui permet à un VPS mutualisé de porter un grand nombre de projets simultanément : le prix marginal d'un projet supplémentaire dépend uniquement de ce qu'il active réellement.

## 6. Faire Évoluer un Projet

Activer ou désactiver un module n'est jamais une réécriture — c'est une **mise à jour du `.env`** suivie d'un redéploiement :

1. **Mise à jour du `.env`** : basculer le(s) flag(s) `MODULE_*` concerné(s).
2. **Alembic upgrade** : les tables nécessaires au(x) nouveau(x) module(s) sont créées (chaque module porte sa propre chaîne de migrations, Chap 6).
3. **Rebuild et déploiement** : `docker compose build && docker compose up -d`.

Chaque changement est **réversible** tant qu'on ne détruit pas de données — un retour au `.env` précédent suivi d'un Alembic downgrade suffit à revenir en arrière.

> **Outillage (round outillage)** : `scripts/toggle_module.sh <module> <on|off>`, livré dans chaque projet généré, fait les étapes ci-dessus en une seule commande — flag `.env`, **flag `.copier-answers.yml`**, `docker compose run --rm migrate`, redémarrage du backend — et vérifie via `/health` que le nouvel état est bien pris en compte avant de déclarer la réussite. `module_fleet` en est explicitement exclu : `docker-compose.yml` a besoin de montages hôte dédiés (Chap 27) qu'un simple changement de `.env` ne peut pas ajouter — seul `copier update` avec `modules: {fleet: true}` régénère le compose correctement pour ce module-là.
>
> **Bug de prod réel, corrigé le jour même où trouvé** : la première version de ce script ne touchait que `.env`. `copier update` re-rend `.env.jinja` depuis la réponse `modules:` **stockée** dans `.copier-answers.yml` — jamais depuis le contenu actuel de `.env` — donc un `copier update` ultérieur (même pour une tout autre raison, ex. un round sans rapport) écrasait silencieusement le flag tout juste basculé. Trouvé le lendemain sur politique-ia : `MODULE_ADMIN` était repassé à `false` après un `copier update` du round suivant. Le script met désormais à jour les deux fichiers dans le même geste.

Publier un projet (`draft` → `preview` → `live`) est une décision séparée du choix de modules — elle est couverte au Chap 19 (fleet dashboard) et Chap 24 (Studio), et gérée par domaine plutôt que par palier : un sous-domaine mutualisé de la flotte peut passer en ligne automatiquement si les guardrails passent, un domaine dédié exige toujours une approbation humaine (blast radius plus élevé).

## 7. Principes de Sélection des Modules

**N'activer que ce que le projet utilise réellement.** Chaque module actif est une route de plus à sécuriser, une migration de plus à maintenir. Un module activé « au cas où » sans usage réel est un coût permanent pour un bénéfice nul.

**Retirer un module devenu inutile.** Un flag qu'on n'ose plus désactiver par peur de casser quelque chose est un signal qu'il manque de tests — le retirer doit être aussi sûr que l'activer.

**Le nombre de modules actifs n'est pas un indicateur de maturité.** Un projet avec deux modules actifs n'est pas « moins avancé » qu'un projet qui en a huit — les deux peuvent être en pleine production, avec des besoins simplement différents.

## Checklist du Chapitre

- [ ] Je sais quels modules mon projet active et pourquoi chacun est nécessaire
- [ ] Je connais la distinction entre le socle core (auth + SEO, toujours présent) et les modules optionnels
- [ ] Je sais que chaque projet a systématiquement sa propre base PostgreSQL, indépendamment de ses modules
- [ ] Je retire un module dès qu'il n'est plus utilisé, plutôt que de le laisser actif « au cas où »
- [ ] Je sais où se décide le cycle de vie d'un projet (Chap 20) et sa publication (Chap 19/24), séparément du choix de modules

---

*Ce catalogue structure tout le reste de l'ouvrage : la Partie II décrit le core présent dans tout projet, la Partie III les modules optionnels que chaque projet active selon ses besoins, et la Partie IV le générateur et la flotte qui rendent l'ensemble opérationnel à grande échelle. Dans le prochain chapitre, nous détaillons l'initialisation du backend FastAPI, socle commun à tout projet.*
