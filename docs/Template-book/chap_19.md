# Fleet Dashboard : la Vue Unifiée de la Flotte

## Introduction

Le fleet dashboard est **l'app séparée** qui donne à l'opérateur la vue unifiée de tous les projets de sa flotte : leur tier, leur stage funnel, leurs métriques de traction, leur coût cumulé, leur candidat au kill mechanism.

Sans ce dashboard, opérer une flotte de 30 projets exige de se souvenir de chaque projet individuellement, de consulter des logs éparpillés, et de rater les signaux faibles qui doivent déclencher une promotion ou un kill. Avec le dashboard, tout tient sur une page.

Le fleet dashboard est déployé sur le domaine premier `mystudio.com` (contrairement aux projets qui vivent sur `*.mystudio.com`) et n'est accessible qu'à l'opérateur de la flotte.

## Architecture

Le fleet dashboard est lui-même un projet GitSky T2 avec des modules spéciaux :

- `MODULE_AUTH=true` — un unique compte admin (l'opérateur).
- `MODULE_ADMIN=true` — l'ensemble des surfaces est admin.
- `MODULE_FLEET=true` — module dédié qui agrège les données de tous les projets.

Le module `fleet` interroge :

- La base du **landing collector** pour les métriques T0.
- Les **APIs de santé** de chaque projet pour connaître leur état.
- Les **logs du LLM proxy** pour le coût IA par projet.
- Le **compte Stripe partagé** pour le revenu par projet.
- Le **service Docker** local pour l'état des conteneurs.

Aucune donnée n'est dupliquée dans la base du fleet dashboard — il consulte les sources en temps réel et agrège en mémoire (cache court côté serveur).

## Vue Principale : la Grille de Projets

L'écran d'accueil est une grille où chaque ligne représente un projet :

| Projet | Tier | Sous-domaine | Signups (14j) | Conversion | RAM | Coût 30j | Signal |
|---|---|---|---|---|---|---|---|
| pain-scraper | T0 | pain-scraper.mystudio.com | 47 | 4,2 % | 55 Mo | 12 € | ✅ promotable |
| code-reviewer-pro | T2 | code-reviewer-pro.com | — | — | 890 Mo | 340 € | — |
| gitsky-app | T2 | gitsky.mystudio.com | — | — | 720 Mo | 180 € | — |
| dead-idea-42 | T0 | dead-idea-42.mystudio.com | 3 | 0,4 % | 45 Mo | 89 € | ❗ pending kill |
| … 26 autres projets | | | | | | | |

Les colonnes sont triables. Un filtre en tête de tableau permet d'isoler par tier, par statut, ou par candidat au kill.

## Onglets Détaillés par Projet

Un clic sur un projet ouvre une vue détaillée à onglets.

### Funnel

Reprend les critères de promotion du Chap 2 sous forme de jauges :

- Visites cumulées, avec objectif ≥ 500 pour la mesure de conversion.
- Signups, avec seuil de promotion T0 → T1 à ≥ 30.
- Retours qualitatifs (extraits de la table `feedbacks` du landing collector).
- Barre visuelle "J+21 restants" avec compte à rebours avant kill.

### Métriques

Timelines `recharts` :

- Signups par jour.
- Visites par jour.
- Coût cumulé (traffic + infra + LLM).
- Rétention D7 (à partir du T1).

### Logs et Événements

Agrégation des dernières entrées `SecurityEvent`, appels LLM significatifs, webhooks Stripe reçus, alertes du cron `kill_check`.

### Actions

Actions manuelles disponibles à l'opérateur :

- **Promouvoir de tier** (avec confirmation) : redéploie le projet avec le nouveau `.env`.
- **Kill maintenant** : lance la procédure du Chap 2, section Kill Mechanism.
- **Sauvegarder maintenant** : force un dump manuel de la base.
- **Voir les logs live** : ouvre un flux `docker logs` streamé.

## Sources de Données du Dashboard

Aucune métrique du fleet dashboard n'est calculée sur des données stockées localement — tout provient d'agrégations en direct des sources autoritatives. Voici où chaque métrique est puisée :

| Métrique | Source | Méthode d'accès | Latence typique |
|---|---|---|---|
| Signups T0 (14 j) | Table `leads` du landing collector | SELECT count avec filtre `project` + `created_at` | < 100 ms |
| Conversion T0 | Table `leads` + count visites landing | Ratio calculé à la demande | < 200 ms |
| Visites 30 j | Table `visits` (module analytics) OU landing collector | Routage selon `MODULE_ANALYTICS` actif | < 200 ms |
| Rétention D7 | Table `visits` avec `ip_hash` + `user_id` | Cohortes calculées par projet | 1-3 s |
| RAM par projet | `docker stats --no-stream --format` | Exec Docker CLI | < 500 ms |
| Coût 30 j — trafic | Aucune source automatique | **Saisie manuelle** par l'opérateur | — |
| Coût 30 j — infra | Amortissement VPS × part RAM du projet | Calcul (`VPS_MONTHLY / total_ram × project_ram`) | < 50 ms |
| Coût 30 j — LLM | Table `spend_logs` du LLM proxy (LiteLLM) | SELECT sum avec filtre `key_alias` | < 200 ms |
| Coût 30 j — Stripe fees | Table `purchases` + taux Stripe standard | Calcul dérivé | < 200 ms |
| MRR | Table `subscriptions` + `Product.price_cents` | SUM des abonnements actifs | < 300 ms |
| Signal kill | Composite des 3 signaux du Chap 2 + delta J+21 | Calcul dérivé, cache 1 h | < 500 ms |
| Dernière sauvegarde OK | Fichier `/backups/last-success.log` par projet | Lecture disque | < 100 ms |
| État Docker | `docker ps --format` | Exec Docker CLI | < 300 ms |
| Événements sécurité | Tables `security_events` de tous les projets | Requête cross-DB | 1-2 s |

**Le principe : pas de duplication.** Le fleet dashboard n'a pas sa propre table de métriques. Il consulte les sources en temps réel avec un cache Redis court (30 s à 5 min selon la volatilité). Cela garantit qu'un projet supprimé disparaît immédiatement du dashboard sans opération de nettoyage manuelle.

**Deux exceptions à cette règle :**

- La table `fleet_lifecycle_events` (voir Chap 20) est propriété du dashboard — c'est le seul journal transversal persistant.
- La table `fleet_manual_costs` accueille les saisies opérateur pour trafic payant (Google Ads, Meta Ads…) qu'aucun système n'expose de manière programmable par projet.

### Pourquoi le Coût Trafic est Manuel

Aucun réseau publicitaire (Google Ads, Meta Ads, Reddit Ads…) n'expose de facturation aisément programmable par projet. L'opérateur saisit les dépenses hebdomadaires par projet dans un formulaire léger. Automatiser cela demanderait des intégrations fragiles pour un gain marginal — c'est un choix d'architecture délibéré.

### Consulter les Leads Captés

Au-delà du compte agrégé « Signups T0 (14 j) », un onglet **Leads** du dashboard permet à l'opérateur de choisir un projet T0 et de consulter la liste brute des emails captés sur sa landing (`GET /leads/{project}` sur le landing collector, triée par date décroissante). Toujours pas de duplication : le fleet dashboard ne stocke rien, il interroge le landing collector à la demande.

La lecture se fait exclusivement via le réseau Docker interne (`shared-services-net`), jamais via une route Traefik/Internet — le landing collector reste strictement injoignable depuis l'extérieur, capture y compris. Seul le module `fleet` (donc uniquement le dashboard lui-même, jamais un projet T0/T1/T2 ordinaire) rejoint ce réseau et porte le jeton `COLLECTOR_STATS_TOKEN` partagé avec le landing collector.

## Les Alertes Automatiques

Le module `fleet` exécute plusieurs crons qui alimentent une file d'alertes :

| Alerte | Déclencheur | Sévérité |
|---|---|---|
| `pending_kill` | J-2 avant expiration T0 sans signal | medium |
| `budget_exceeded` | Coût cumulé au-delà du plafond du tier | high |
| `security_high` | ≥ 10 événements `critical` en 24h sur un projet | high |
| `deployment_failed` | Un projet ne répond plus à `/health` depuis 5 min | critical |
| `llm_quota_hit` | Un projet atteint 90 % de son quota LLM mensuel | medium |
| `template_outdated` | Un correctif de template n'a pas été propagé après 30 j | low |

Ces alertes sont visibles dans une barre latérale permanente. Elles ne génèrent **pas d'emails individuels** — l'opérateur consulte le dashboard à un rythme quotidien fixe (recommandation : matin, 10 min).

## Métriques Agrégées de Flotte

Un onglet "Overview" affiche les KPI de la flotte entière :

- **Taux de survie global** : pourcentage de projets qui montent d'un tier.
- **Coût mensuel total** (infra + LLM + Stripe fees).
- **Revenu mensuel total** (MRR + achats one-off).
- **Marge nette** de la flotte.
- **Empreinte RAM cumulée** vs capacité du VPS.

Ces KPI permettent de décider si la flotte doit être élargie (racheter des idées à harvester), consolidée (kill des projets zombies), ou faire l'objet d'un scale-up (VPS plus gros).

## Le Fleet Dashboard comme Contrat

Un projet n'est pas "vivant" dans la flotte tant qu'il n'est pas enregistré dans le fleet dashboard. Le générateur `create-gitsky-project` (Chap 17) inscrit automatiquement chaque nouveau projet lors de sa génération via un `POST /api/fleet/projects/register`.

Cette convention garantit qu'aucun projet ne peut exister « en dehors » du dashboard, échappant au kill mechanism ou à la comptabilité budgétaire.

**Cet endpoint est protégé.** `register` n'est pas une route utilisateur (le générateur n'a ni compte ni JWT) : elle est gardée par un **token partagé machine-à-machine**, exigé dans l'en-tête `X-Fleet-Token` et comparé à `FLEET_REGISTER_TOKEN` (comparaison à temps constant). Le générateur l'envoie depuis son environnement. Même sémantique que les autres stubs du châssis : ouvert en développement sans token, mais **fail-closed** en production — un token non configuré fait répondre `503`, jamais un register public. Sans ce garde-fou, n'importe qui pouvait créer ou **écraser** (tier, domaine) les projets de la flotte. La lecture des stats du landing collector (Chap 18) suit exactement le même modèle (`X-Collector-Token`).

## Un Kill est un Événement du Dashboard, pas un Script Manuel

L'exécution du kill mechanism passe **toujours** par le dashboard, jamais par un `docker compose down` ad hoc — sinon l'archivage, la libération des ressources et la journalisation ne se font pas. Cette discipline est ce qui permet aux calculs de ROI de flotte de rester justes à long terme.

---

*L'opérateur voit sa flotte, décide sur chaque projet. Le prochain chapitre formalise ces décisions dans le cycle de vie complet d'un projet, du harvest initial à l'archivage ou au succès.*
