# Fleet Dashboard : la Vue Unifiée de la Flotte

## Introduction

Le fleet dashboard est **l'app séparée** qui donne à l'opérateur la vue unifiée de tous les projets de sa flotte : leurs modules actifs, leur état de santé, leur coût cumulé, leurs événements de sécurité récents, et — depuis le Chap 27 — l'assistant qui permet d'en créer de nouveaux.

Sans ce dashboard, opérer une flotte de 30 projets exige de se souvenir de chaque projet individuellement, de consulter des logs éparpillés, et de rater les signaux qui devraient déclencher une décision (coût inhabituel, panne prolongée, incident de sécurité). Avec le dashboard, tout tient sur une page.

Le fleet dashboard est déployé sur le domaine premier `mystudio.com` (contrairement aux projets qui vivent sur `*.mystudio.com`) et n'est accessible qu'à l'opérateur de la flotte.

## Architecture

Le fleet dashboard est lui-même un projet GitSky avec des modules spéciaux :

- `MODULE_AUTH=true` — un unique compte admin (l'opérateur).
- `MODULE_ADMIN=true` — l'ensemble des surfaces est admin.
- `MODULE_FLEET=true` — module dédié qui agrège les données de tous les projets. Ce module n'a de sens que sur l'app qui pilote la flotte — jamais activé sur un projet applicatif ordinaire.

Le module `fleet` interroge :

- Les **APIs de santé** de chaque projet pour connaître leur état.
- Les **logs du LLM proxy** pour le coût IA par projet.
- Le **compte Stripe partagé** pour le revenu par projet.
- Le **service Docker** local pour l'état des conteneurs.
- L'**historique de déploiement GitHub** (Chap 26) pour la fraîcheur du code déployé.

Aucune donnée n'est dupliquée dans la base du fleet dashboard — il consulte les sources en temps réel et agrège en mémoire (cache court côté serveur).

## Vue Principale : la Grille de Projets

L'écran d'accueil est une grille où chaque ligne représente un projet :

| Projet | Modules actifs | Domaine | Statut | RAM | Coût 30j | Santé |
|---|---|---|---|---|---|---|
| pain-scraper | auth, admin, analytics | pain-scraper.mystudio.com | actif | 180 Mo | 12 € | ✅ |
| code-reviewer-pro | auth, admin, analytics, agentic, monétisation | code-reviewer-pro.com | actif | 890 Mo | 340 € | ✅ |
| gitsky-app | auth, admin, i18n | gitsky.mystudio.com | actif | 220 Mo | 18 € | ✅ |
| ancien-projet | auth | — | archivé | — | — | — |
| … 26 autres projets | | | | | | |

Les colonnes sont triables. Un filtre en tête de tableau permet d'isoler par statut (actif/archivé), par module actif, ou par état de santé.

## Onglets Détaillés par Projet

Un clic sur un projet ouvre une vue détaillée à onglets.

### Aperçu

- Modules actifs et leur date d'activation.
- Domaine(s) rattachés, dépôt GitHub lié, dernière date de déploiement (Chap 26).
- Version de template — à jour ou en attente d'un `copier update` (Chap 17).

### Métriques

Timelines `recharts` :

- Visites et signups par jour (si le module analytics ou le landing collector optionnel sont utilisés — Chap 18 §3).
- Coût cumulé (trafic + infra + LLM).
- MRR, si la monétisation par abonnement est active.

### Logs et Événements

Agrégation des dernières entrées `SecurityEvent`, appels LLM significatifs, webhooks Stripe reçus, et historique des déploiements déclenchés par push GitHub (Chap 26).

### Actions

Actions manuelles disponibles à l'opérateur :

- **Activer/désactiver un module** (avec confirmation) : redéploie le projet avec le `.env` mis à jour.
- **Redéployer maintenant** : rejoue le pipeline de déploiement du Chap 26 à la demande, utile pour un projet dont le dépôt n'a pas de webhook actif.
- **Archiver le projet** : lance la procédure du Chap 20, section Archivage.
- **Sauvegarder maintenant** : force un dump manuel de la base.
- **Voir les logs live** : ouvre un flux `docker logs` streamé.

## Sources de Données du Dashboard

Aucune métrique du fleet dashboard n'est calculée sur des données stockées localement — tout provient d'agrégations en direct des sources autoritatives. Voici où chaque métrique est puisée :

| Métrique | Source | Méthode d'accès | Latence typique |
|---|---|---|---|
| Signups (14 j) | Table `leads` (landing collector optionnel) ou table `users` du projet | SELECT count avec filtre `project`/`created_at` | < 100 ms |
| Visites 30 j | Table `visits` (module analytics) ou landing collector | Routage selon `MODULE_ANALYTICS` actif | < 200 ms |
| RAM par projet | `docker stats --no-stream --format` | Exec Docker CLI | < 500 ms |
| Coût 30 j — trafic | Aucune source automatique | **Saisie manuelle** par l'opérateur | — |
| Coût 30 j — infra | Amortissement VPS × part RAM du projet | Calcul (`VPS_MONTHLY / total_ram × project_ram`) | < 50 ms |
| Coût 30 j — LLM | Table `spend_logs` du LLM proxy (LiteLLM) | SELECT sum avec filtre `key_alias` | < 200 ms |
| Coût 30 j — Stripe fees | Table `purchases` + taux Stripe standard | Calcul dérivé | < 200 ms |
| MRR | Table `subscriptions` + `Product.price_cents` | SUM des abonnements actifs | < 300 ms |
| Dernière sauvegarde OK | Fichier `/backups/last-success.log` par projet | Lecture disque | < 100 ms |
| État Docker | `docker ps --format` | Exec Docker CLI | < 300 ms |
| Événements sécurité | Tables `security_events` de tous les projets | Requête cross-DB | 1-2 s |
| Dernier déploiement | Historique webhook GitHub (Chap 26) | Table `fleet_lifecycle_events` | < 100 ms |

**Le principe : pas de duplication.** Le fleet dashboard n'a pas sa propre table de métriques applicatives. Il consulte les sources en temps réel avec un cache Redis court (30 s à 5 min selon la volatilité). Cela garantit qu'un projet archivé disparaît immédiatement de la vue active sans opération de nettoyage manuelle.

**Deux exceptions à cette règle :**

- La table `fleet_lifecycle_events` (voir Chap 20) est propriété du dashboard — c'est le seul journal transversal persistant (création, redéploiement, archivage, mise à jour de template).
- La table `fleet_manual_costs` accueille les saisies opérateur pour trafic payant (Google Ads, Meta Ads…) qu'aucun système n'expose de manière programmable par projet.

### Pourquoi le Coût Trafic est Manuel

Aucun réseau publicitaire (Google Ads, Meta Ads, Reddit Ads…) n'expose de facturation aisément programmable par projet. L'opérateur saisit les dépenses hebdomadaires par projet dans un formulaire léger. Automatiser cela demanderait des intégrations fragiles pour un gain marginal — c'est un choix d'architecture délibéré.

### Consulter les Leads Captés

Pour les projets qui utilisent le landing collector optionnel (Chap 18 §3), un onglet **Leads** du dashboard permet à l'opérateur de choisir un projet et de consulter la liste brute des emails captés sur sa landing (`GET /leads/{project}` sur le landing collector, triée par date décroissante). Toujours pas de duplication : le fleet dashboard ne stocke rien, il interroge le landing collector à la demande.

La lecture se fait exclusivement via le réseau Docker interne (`shared-services-net`), jamais via une route Traefik/Internet — le landing collector reste strictement injoignable depuis l'extérieur, capture y compris. Seul le module `fleet` (donc uniquement le dashboard lui-même, jamais un projet applicatif ordinaire) rejoint ce réseau et porte le jeton `COLLECTOR_STATS_TOKEN` partagé avec le landing collector.

## Les Alertes Automatiques

Le module `fleet` exécute plusieurs crons qui alimentent une file d'alertes — toutes informatives, aucune ne déclenche d'action automatique sur le projet :

| Alerte | Déclencheur | Sévérité |
|---|---|---|
| `budget_exceeded` | Coût cumulé au-delà d'un plafond réglé par l'opérateur pour ce projet | high |
| `security_high` | ≥ 10 événements `critical` en 24h sur un projet | high |
| `deployment_failed` | Un projet ne répond plus à `/health` depuis 5 min | critical |
| `llm_quota_hit` | Un projet atteint 90 % de son quota LLM mensuel | medium |
| `template_outdated` | Un correctif de template n'a pas été propagé après 30 j | low |
| `webhook_deploy_failed` | Le dernier déploiement déclenché par push GitHub a échoué (Chap 26) | high |

Ces alertes sont visibles dans une barre latérale permanente. Elles ne génèrent **pas d'emails individuels** — l'opérateur consulte le dashboard à un rythme quotidien fixe (recommandation : matin, 10 min), et décide lui-même s'il y a lieu d'agir (redéployer, ajuster un module, archiver).

## Métriques Agrégées de Flotte

Un onglet "Overview" affiche les KPI de la flotte entière :

- **Nombre de projets actifs / archivés.**
- **Coût mensuel total** (infra + LLM + Stripe fees).
- **Revenu mensuel total** (MRR + achats one-off).
- **Marge nette** de la flotte.
- **Empreinte RAM cumulée** vs capacité du VPS.
- **Fraction de la flotte à jour** du dernier `copier update` (Chap 17).

Ces KPI permettent de décider si la flotte doit être élargie (VPS plus gros ou VPS supplémentaire), consolidée (archivage de projets inactifs repérés manuellement), ou si un correctif de template doit être propagé en priorité.

## Le Fleet Dashboard comme Contrat

Un projet n'est pas "vivant" dans la flotte tant qu'il n'est pas enregistré dans le fleet dashboard. Le générateur `create-gitsky-project` (Chap 17) inscrit automatiquement chaque nouveau projet lors de sa génération via un `POST /api/fleet/projects/register`.

Cette convention garantit qu'aucun projet ne peut exister « en dehors » du dashboard, échappant au suivi de santé ou à la comptabilité budgétaire.

**Cet endpoint est protégé.** `register` n'est pas une route utilisateur (le générateur n'a ni compte ni JWT) : elle est gardée par un **token partagé machine-à-machine**, exigé dans l'en-tête `X-Fleet-Token` et comparé à `FLEET_REGISTER_TOKEN` (comparaison à temps constant). Le générateur l'envoie depuis son environnement. Même sémantique que les autres stubs du châssis : ouvert en développement sans token, mais **fail-closed** en production — un token non configuré fait répondre `503`, jamais un register public. Sans ce garde-fou, n'importe qui pouvait créer ou **écraser** (domaine, modules) les projets de la flotte. La lecture des stats du landing collector (Chap 18) suit exactement le même modèle (`X-Collector-Token`).

## Un Archivage est un Événement du Dashboard, pas un Script Manuel

L'exécution d'un archivage passe **toujours** par le dashboard, jamais par un `docker compose down` ad hoc — sinon la sauvegarde froide, la libération des ressources et la journalisation ne se font pas. Cette discipline est ce qui permet aux calculs de coût de flotte de rester justes à long terme, et à un projet archivé par erreur d'être reconstitué proprement (Chap 20).

---

*L'opérateur voit sa flotte, décide pour chaque projet. Le prochain chapitre formalise ces décisions dans le cycle de vie complet d'un projet, de sa création à son archivage.*
