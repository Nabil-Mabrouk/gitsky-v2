# Cycle de Vie d'un Projet dans la Flotte

## Introduction

> **Écart au livre (Phase 6)** — ce chapitre décrivait auparavant un système de paliers T0/T1/T2 avec promotion automatique sur signal mesurable et un cron `kill_check` qui arrêtait les projets sans surveillance humaine (voir Chap 2 pour le contexte du retrait). Ce mécanisme a disparu : GitSky ne présume plus qu'un projet est une idée en test qu'il faut faire grandir ou tuer selon un score. Le cycle de vie est aujourd'hui volontairement simple, et chaque décision qui compte reste **entre les mains d'un opérateur humain**.

Ce chapitre décrit le cycle de vie complet d'un projet GitSky : sa création, sa vie active (modules, publication), son archivage, et les trajectoires qui l'en font sortir (migration de domaine, émancipation, cession). Il s'appuie sur le fleet dashboard (Chap 19) pour les actions opérateur et sur le catalogue de modules (Chap 2) pour ce qui peut changer en cours de route.

## Vue d'Ensemble

```text
   Création          Vie active                    Archivage
  (générateur,   ──►  (modules activables,   ──►   (manuel, décision
   Chap 17)            publication draft/            opérateur,
                        preview/live,                 Chap 19)
                        Chap 2 §6 / Chap 24)
```

Contrairement à l'ancien système, il n'y a **aucune fenêtre de temps, aucun seuil de coût, aucun signal mesuré automatiquement** qui fait avancer un projet d'un stage à l'autre. Un projet reste actif indéfiniment tant qu'un opérateur ne décide pas explicitement de l'archiver.

## Création

Un projet naît via le générateur (Chap 17) : nom, choix de modules (Chap 2), domaine, puis `copier copy && docker compose up -d`. Il s'enregistre lui-même auprès du fleet dashboard (`register_fleet.py`, Chap 19) et apparaît dans la grille avec le statut `active`.

À ce stade, l'automatisation s'arrête là où le générateur produit un projet fonctionnel — la création d'un dépôt GitHub dédié et son premier push restent une étape manuelle pour l'instant (voir Chap 26 pour ce qui est déjà automatisé côté intégration continue, et ce qui ne l'est pas encore).

## Vie Active

Un projet actif peut évoluer sur deux axes indépendants, sans qu'aucun des deux ne soit contraint par l'autre :

**Ses modules** — activer ou désactiver un `MODULE_*` à tout moment (Chap 2 §6). Ce n'est jamais une « promotion », juste une mise à jour de configuration suivie d'un redéploiement.

**Son statut de publication** — `draft` → `preview` → `live`, géré par `evaluate_promotion` (Chap 19, Chap 24). Le passage en `live` est automatique si le projet est encore sur un sous-domaine de la flotte (`*.mystudio.com`) et que les guardrails passent ; il exige une approbation humaine explicite dès qu'un domaine dédié est en jeu — le blast radius d'un domaine premier (souvent une campagne payante, un budget engagé) justifie la revue qu'un sous-domaine jetable n'a pas besoin d'exiger.

Ces deux axes sont journalisés indépendamment dans `fleet_lifecycle_events` (voir §Journal de la Flotte ci-dessous).

## Archivage

Un projet s'archive **uniquement sur décision d'un opérateur**, depuis le fleet dashboard (`POST /api/fleet/projects/{name}/archive`, réservé aux comptes admin). L'action est idempotente : réarchiver un projet déjà archivé ne journalise pas d'événement supplémentaire.

**Ce que l'archivage fait aujourd'hui :** marque le projet `archived`, exclu dès lors du monitoring de disponibilité (`health_monitor.py` ignore les projets archivés — une archive n'est pas une panne) et de la grille par défaut. **Depuis le round sécurisation (Chap 23)**, il journalise aussi `stop_requested` : `lifecycle-fleet.sh` (shared_services), qui tourne sur l'hôte avec un accès Docker réel, exécute alors un vrai `docker compose down` pour ce projet — les conteneurs s'arrêtent réellement, plus seulement le flag DB.

**Ce que l'archivage ne fait toujours pas :** il ne retire aucun label Traefik (inutile : `docker compose down` retire déjà les conteneurs, donc leurs labels — Traefik ne peut plus router vers rien), ne libère aucun domaine (DNS reste entièrement manuel, hors du périmètre de GitSky), ne déclenche aucune sauvegarde froide dédiée. Documenter cet écart plutôt que le taire reste volontaire.

Il n'existe pas non plus, à ce stade, d'action « réactiver » dédiée qui repasserait le statut à `active` — mais `POST /api/fleet/projects/{name}/start` (voir section suivante) redémarre bien les conteneurs d'un projet archivé ; seul le flag `status` en base reste à corriger à la main en attendant qu'un endpoint combine les deux.

## Cycle de vie opérationnel : arrêt, démarrage, maintenance

Round sécurisation (Chap 23) : au-delà de l'archivage (une décision définitive), la fiche projet du dashboard offre trois actions réversibles, réservées aux comptes admin :

| Endpoint | Effet réel |
|---|---|
| `POST /projects/{name}/stop` | `docker compose down` — conteneurs arrêtés, image conservée |
| `POST /projects/{name}/start` | `docker compose up -d` — redémarrage à l'identique, pas de rebuild |
| `POST /projects/{name}/maintenance` | `docker compose down` PUIS démarre `docker-compose.maintenance.yml` (une page statique nginx, aucune dépendance backend) sur les MÊMES routes Traefik que le frontend/backend réels |
| `DELETE /projects/{name}/maintenance` | l'inverse : arrête la page de maintenance, redémarre l'app réelle |

Même architecture que le déploiement continu (Chap 26) : le dashboard n'a **aucun accès Docker** (conteneur public-facing, surface d'attaque minimale) — ces quatre endpoints ne font que journaliser l'intention dans `fleet_lifecycle_events`. C'est `shared_services/scripts/lifecycle-fleet.sh`, un cron hôte (`crontab.fleet`, toutes les 2 minutes) avec un accès Docker réel, qui exécute l'action via `GET /api/fleet/lifecycle/pending` — même contrat texte brut, même curseur local que `/deploys/pending`.

L'état affiché sur la fiche projet et la grille (`lifecycle_state` : `normal`/`stopped`/`maintenance`) est calculé à la volée depuis le dernier événement pertinent journalisé — pas une colonne DB séparée, même principe que `health` (`health_monitor.bulk_health_status`, Chap 28).

## Migration Sous-Domaine → Domaine Premier

Quand un opérateur décide qu'un projet mérite son propre domaine (`pain-scraper.com` au lieu de `pain-scraper.mystudio.com`), la migration doit préserver le SEO déjà acquis et ne pas casser les liens partagés par des utilisateurs. Voici la procédure en quatre étapes.

### Étape 1 — Provisionnement du Nouveau Domaine (J-7)

- Achat du domaine.
- Configuration DNS chez le registrar :
  - Enregistrement `A` pointant vers l'IP du VPS.
  - Enregistrements `MX` vers le SMTP relay partagé si le projet reçoit des emails.
  - Enregistrement `CAA` autorisant Let's Encrypt.
- Ajout des labels Traefik du projet pour accepter les **deux domaines simultanément**.
- Génération du certificat pour le nouveau domaine (Let's Encrypt HTTP-01 standard — pas DNS-01 puisque ce n'est pas un wildcard).

À ce stade, les deux URLs répondent — l'ancienne reste primaire, la nouvelle est en accueil.

### Étape 2 — Préparation SEO (J-4)

- Email aux utilisateurs annonçant le nouveau domaine (motif : identité de marque forte).
- Mise à jour du `canonical` de toutes les pages pour pointer vers le **nouveau** domaine (via composant SEO du Chap 10).
- Mise à jour du `sitemap.xml` pour lister les URLs sous le nouveau domaine.
- Soumission du sitemap à Google Search Console pour le nouveau domaine, revendication de propriété.

Le `canonical` pointant vers le nouveau signale à Google la préférence sans encore casser l'ancien.

### Étape 3 — Bascule Primaire (J-0)

- Inversion du `PROJECT_DOMAIN` dans le `.env` : le nouveau domaine devient primaire.
- L'ancien sous-domaine renvoie désormais une **redirection 301** vers le nouveau, gérée par un middleware Traefik :

```yaml
labels:
  - "traefik.http.middlewares.redirect-old.redirectregex.regex=^https://pain-scraper.mystudio.com/(.*)"
  - "traefik.http.middlewares.redirect-old.redirectregex.replacement=https://pain-scraper.com/$${1}"
  - "traefik.http.middlewares.redirect-old.redirectregex.permanent=true"
```

- Envoi d'un email de confirmation aux utilisateurs.

### Étape 4 — Suivi (J+30)

- Vérification que Google indexe le nouveau domaine et déprécie l'ancien.
- Vérification du trafic organique : la baisse initiale (~30-40 %) doit se résorber en 6-8 semaines.
- L'ancien sous-domaine reste actif **en redirection au moins 12 mois** — jamais supprimé tant que des liens externes peuvent exister.

### Anti-Patterns à Éviter

- **Suppression brutale du sous-domaine** — casse tous les liens externes accumulés, perte SEO définitive.
- **Absence de redirection 301** — Google traite le nouveau domaine comme un site vierge, perte de tout le PageRank.
- **Migration pendant une campagne active** — la baisse SEO temporaire tue le rendement des campagnes en cours.

### Timing Recommandé

Idéal : avant le lancement d'une grosse acquisition (Product Hunt, article invité, campagne payante) qui ferait converger du trafic vers l'ancien domaine — pas pendant.

## Émancipation : Sortir un Projet de la Flotte

Un projet qui a suffisamment grandi peut justifier de sortir de l'infrastructure mutualisée. C'est une décision d'opérateur, pas un seuil automatique.

### Option A — Rester dans la flotte

Le cas par défaut : le projet continue à bénéficier des services partagés (Postgres, Traefik, SMTP, LLM proxy) tant que rien ne justifie d'en sortir.

### Option B — Émancipation

L'opérateur peut décider de sortir le projet de la flotte partagée :

- Migration vers un compte Stripe propre (rattachement à une entité juridique dédiée — voir Chap 16 §considérations légales).
- Migration vers un VPS dédié (ou cluster).
- Extraction de la base PostgreSQL du service partagé vers une base dédiée.
- Retrait des labels Traefik du proxy partagé.

Cette procédure est décrite dans le playbook `docs/emancipation.md` du repo `startup-factory-configs/`. Elle est réversible en cas de sur-anticipation.

### Option C — Vente ou acqui-hire

Un projet à traction significative peut être vendu. La flotte étant conçue avec isolation stricte (une DB, un domaine, un compte Stripe metadata-namespacé), cette extraction est mécanique.

## Le Journal de la Flotte

Chaque événement du cycle de vie est journalisé dans `fleet_lifecycle_events`, interrogeable depuis le fleet dashboard. Le vocabulaire actuel :

| `event_type` | Déclenché par |
|---|---|
| `born` | Enregistrement initial (`register_fleet.py`, à la création) |
| `publish_preview` / `publish_live` | Changement de statut de publication (`evaluate_promotion`, Chap 19/24) |
| `deployment_failed` / `deployment_recovered` | Poller de disponibilité (`fleet-health.sh`, Chap 23) |
| `archived` | Archivage manuel par un opérateur (ce chapitre) |
| `deploy_triggered` | Push GitHub vérifié sur la branche de déploiement (Chap 26) |

Contrairement à l'ancien système, ce journal ne sert plus à calculer un taux de survie T0 → T1 → T2 — il n'y a plus de paliers à comparer. Il reste néanmoins la source de vérité pour tout audit : reconstituer l'historique complet d'un projet (quand il a été créé, quand il a changé de statut, quand un déploiement a échoué, quand il a été archivé) sans avoir à recouper plusieurs logs.

---

*Ce chapitre clôt la partie industrialisation. La dernière partie du livre couvre la production et la maintenance : configuration du serveur Ubuntu, sauvegardes de flotte, intégration GitHub et bonnes pratiques opérationnelles.*
