# Roadmap : GitSky → Framework Multi-Projets Généraliste

*Document de travail — état au 2026-08-26. Rédigé après lecture complète du livre (`docs/Template-book/`) et du code existant (`src/`). Aucune modification de code ni du livre n'a encore été faite : ce document sert de base de décision avant de lancer les phases d'implémentation ci-dessous, une par une.*

## Contexte

Ce dépôt contient déjà **GitSky** : un système "startup-factory" documenté (`docs/Template-book/`, 25 chapitres) et partiellement implémenté (`src/generator/`, `src/shared_services/`, ~60 fichiers pytest) — Traefik + un conteneur PostgreSQL par projet + un template FastAPI/React avec modules optionnels, piloté par un générateur Copier, agrégé dans un Fleet Dashboard, appuyé sur des services partagés et un playbook de durcissement/maintenance production déjà rédigé.

L'objectif exprimé : transformer ceci en framework général pour héberger **de nombreux projets web indépendants** (pas des idées de startup en test) sur un même serveur, avec un dashboard moderne et sécurisé pour suivre l'activité/la maintenance/la sécurité, une isolation par conteneur par projet, un template partagé avec modules au choix (landing, gestion utilisateurs, boutique, admin, tutoriels/doc, …), et un flux de création simple : nom + modules + repo GitHub + domaine → déploiement instantané, puis personnalisation et re-synchronisation.

Décisions confirmées (échange de clarification du 2026-08-26) :

1. **Faire évoluer ce dépôt sur place**, plutôt que repartir de zéro.
2. **Supprimer entièrement les tiers T0/T1/T2**, et le mécanisme de kill/promotion automatique qui va avec. Chaque projet active simplement les modules dont il a besoin à la création ; pas de scoring de croissance, pas d'arrêt automatique. Un opérateur archive/supprime un projet manuellement depuis le dashboard.
3. **Intégration GitHub : automatisation complète par défaut** (le dashboard crée le repo via l'API GitHub, pousse le projet généré, configure un webhook pour un redéploiement automatique à chaque push), **avec un mode de rattachement manuel** (lier un repo déjà existant).
4. **Le catalogue de modules existant est conservé en totalité** : landing (core), auth/gestion utilisateurs (core), admin, monétisation/boutique, tutoriels/doc, analytics, sécurité, onboarding, plus le framework agentic IA — tous sélectionnables indépendamment, sans verrouillage par tier.

Convention du dépôt (`CLAUDE.md`) : *« le livre fait foi — si le développement diverge du plan, on s'arrête et on tranche avant de modifier le livre »*. Supprimer les tiers est une divergence délibérée et désormais confirmée par rapport à la prémisse du Chapitre 2 — **le livre doit donc être mis à jour dans le cadre du travail**, pas laissé silencieusement incohérent avec le code.

## Ce qui est déjà vrai aujourd'hui (vérifié en lisant le code, pas seulement le livre)

- `src/generator/copier.yml` + `src/generator/extensions/context.py` (`TierResolver`) : résout `project.tier` en profil de `MODULE_FLAGS` (dict `TIER_PROFILES`), calcule `gunicorn_workers` via `WORKERS_BY_TIER` — copie vendorisée de la même table dans `app/core/config.py` (`Settings.apply_tier_defaults`).
- `docker-compose.yml.jinja` : branche sur `gitsky_tier == "t0"` pour `DATABASE_URL` (SQLite vs Postgres) et omet entièrement les services `db`/`migrate` pour T0.
- `app/modules/fleet/` : `models.py` (`Project.tier`, `FleetLifecycleEvent`), `kill_check.py` (fonctions d'évaluation pures par tier), `router.py` (routes `/kill-check`, `/promote`, `publish.evaluate_promotion` qui verrouille la publication par tier).
- Tests directement liés aux tiers : `test_config_tiers.py`, `test_kill_check.py`, `test_generator_spike.py`, `test_fleet_router.py`, `test_compose_prod.py`, `test_publish.py`, plus des assertions de tier disséminées dans `test_fleet_scripts.py`, `test_docker_prod*.py`.
- Le générateur est aujourd'hui **CLI uniquement** (`copier copy --data-file config.yaml <template> <dest>`), invoqué à la main ou par les scripts `_tasks` (actuellement **simulés** — `src/generator/tasks/provision_db.py`, `register_fleet.py`, `apply_migrations.py` sont explicitement marqués « SIMULÉ », à connecter à la vraie infra).
- **Aucune intégration API GitHub** n'existe encore dans le code (pas de création de repo, pas de récepteur de webhook, pas de pipeline push-to-deploy). La FAQ du Chap 22 ne couvre qu'un clone manuel sur le VPS.
- Le frontend du dashboard (`frontend/src/pages/admin/*`, `FleetGrid.tsx`) est fonctionnel (tableaux, onglets) mais n'a pas encore reçu la passe de design "moderne" demandée.

## Architecture cible recommandée (remplacement des tiers)

Remplacer « tier » par un **catalogue de modules à plat** : `landing`/`auth` deviennent du core toujours actif (pas de flag, comme `seo` déjà aujourd'hui), et chaque autre module (`admin`, `analytics`, `onboarding`, `tutorials`, `security_middleware`, `i18n`, `agentic`, `monetization_shop`, `monetization_subscription`) est un booléen indépendant que l'opérateur règle par projet à la création — sans profil, sans valeur dérivée.

Chaque projet reçoit **son propre conteneur PostgreSQL sans condition** (la branche SQLite réservée à T0 disparaît) — cela supprime la plus grosse source de complexité conditionnelle du template compose et du générateur, et rejoint la préférence déjà affirmée par le livre pour l'isolation par conteneur (Chap 18 §2). `WEB_CONCURRENCY`/le nombre de workers Gunicorn devient une simple valeur de config par projet (défaut raisonnable, ex. 2), réglable à la création, plus dérivée d'un tier.

Le cycle de vie devient : **créé → actif → archivé**. Plus d'états `pending_kill`/`killed` pilotés par un scoring de croissance ; les fonctions d'évaluation de `kill_check.py` et les routes `/kill-check`/`/promote` sont supprimées. `FleetLifecycleEvent` continue d'enregistrer les événements réels (création, archivage, succès/échec de déploiement, mise à jour de template) — seuls les événements pilotés par le scoring disparaissent. Le dashboard garde une action manuelle « Archiver le projet » (arrêt des conteneurs, conservation de la sauvegarde, libération du domaine) comme remplacement humain du kill mechanism, et garde les *alertes* de budget/santé (déjà en partie conçues au Chap 19) comme signaux de décision manuelle plutôt que comme déclencheurs automatiques.

## Feuille de route par phases

### Phase A — Mise à jour du livre (aucun code)
Réécrire le Chapitre 2 (actuellement « Les Trois Tiers ») en un chapitre « Catalogue de Modules » : liste à plat, sans tiers, sans critères de promotion/kill, archivage manuel à la place. Répercuter la modification sur chaque chapitre qui référence les tiers ou le kill mechanism : Chap 1 (tableau d'exemple multi-tenance), Chap 9 (le shell admin n'est plus verrouillé à « T2 par défaut »), Chap 17 (le `config.yaml` du générateur perd `tier:`), Chap 18 (l'exception « T0 sans base propre » du §2 disparaît), Chap 19 (colonne tier du Fleet Dashboard, actions de promotion, section kill mechanism), Chap 20 (réécriture complète — ce chapitre *est* le cycle de vie par tier), Chap 21 (abandonner le cadrage RAM-par-tier, garder la mécanique Docker/workers Gunicorn), Chap 22/23 (peu d'édition — sauvegardes/monitoring/sécurité référencent peu les tiers), Chap 24 (abandonner le cadrage « T0 rendu différemment », garder le contenu Studio/branding), Chap 25 (le guide opérateur actuel raconte un parcours T0→T1→T2 — à réécrire en créer → personnaliser → déployer → maintenir). Ajouter deux nouveaux chapitres pour les capacités réellement nouvelles : **Intégration GitHub & déploiement automatique** (automatisation de repo, pipeline webhook) et **L'Assistant de Création** (parcours UI). Cette phase produit la spécification que les phases B–D implémentent.

### Phase B — Runtime & générateur : suppression des tiers
- `app/core/config.py` : supprimer `TIER_PROFILES`, `gitsky_tier`, `apply_tier_defaults` ; chaque flag `module_*` devient un simple `bool = False` (sauf ceux que le livre désigne comme core toujours actif).
- `src/generator/copier.yml` + `extensions/context.py` : supprimer la logique de profil de `TierResolver` et `WORKERS_BY_TIER` ; le bloc `project` de `config.yaml` perd `tier` ; le bloc `modules` règle les flags directement, sans fusion override-sur-profil.
- `docker-compose.yml.jinja` / `docker-compose.dev.yml.jinja` : supprimer toutes les branches `{% if gitsky_tier == "t0" %}` ; les services `db` + `migrate` deviennent inconditionnels ; `DATABASE_URL` est toujours la version Postgres.
- Mettre à jour chaque fichier de test qui encode un comportement par tier (`test_config_tiers.py` → test des flags de modules ; `test_kill_check.py` → suppression ; `test_generator_spike.py`/`test_compose_prod.py`/`test_fleet_scripts.py` → suppression des branches tier, conservation du reste de leur couverture). Conformément à `CLAUDE.md` : on corrige le code, on ne touche à un test que si son *intention* était vraiment spécifique aux tiers.

### Phase C — Module fleet : suppression du kill mechanism, conservation du registre
- `app/modules/fleet/models.py` : supprimer `Project.tier` ; garder `Project.status` restreint à `active`/`archived` ; garder `FleetLifecycleEvent`/`MaintenanceRun` avec un vocabulaire d'`event_type` allégé.
- Supprimer `kill_check.py` et la route `/kill-check` ; supprimer ou reconvertir `publish.py` (`evaluate_promotion` verrouillé par tier) — un projet est publié ou ne l'est pas, sans échelle d'approbation par tier (sauf à garder l'idée de publication « guardrails-in-the-loop » du Studio comme bascule *manuelle*, non dérivée d'un tier).
- Ajouter une action `/archive` (arrêt de la stack compose, statut `archived`, conservation des sauvegardes, libération du domaine après un délai de grâce) comme remplacement manuel du kill dans le dashboard.

### Phase D — Intégration GitHub (nouvelle capacité)
- Stocker une installation GitHub App au niveau du fleet dashboard (préférable à un PAT brut : scoping, révocable, pas de secret longue-durée dans `.env`) ; `shared_services` reçoit un nouveau petit service (ou un sous-module `fleet`) responsable de : création de repo via l'API GitHub, push initial du projet généré, création du webhook (événements `push` → nouvel endpoint du dashboard).
- Nouvel endpoint (ex. `POST /api/fleet/webhooks/github/{project}`) : vérifie la signature HMAC du webhook GitHub, déclenche le pipeline de déploiement sur un `push` vers la branche par défaut (`git pull` dans le dossier du projet sur le VPS, `copier update` optionnel, `docker compose up -d --build`, puis vérification santé via `/health`), et journalise le résultat dans `FleetLifecycleEvent`.
- Mode de rattachement manuel : un parcours « repo existant » qui saute la création mais propose quand même d'installer le webhook (nécessite que l'opérateur ait les droits admin sur ce repo, sinon repli sur « redéploiement manuel » depuis le dashboard).

### Phase E — Assistant de création (nouvelle capacité, plus gros morceau UI)
- Nouveau parcours dashboard : nom du projet → cases à cocher des modules (catalogue des phases A/B) → GitHub (créer un nouveau / lier un existant) → domaine → récapitulatif → « Créer & Déployer ».
- Backend : un endpoint `POST /api/fleet/projects` qui assemble côté serveur le payload `config.yaml` à partir des données du formulaire, invoque le générateur Copier de façon programmatique (API Python `copier.run_copy`, pas un appel CLI shell-out — plus sûr pour contrôler la portée de `unsafe=True`/`--trust`), puis passe la main au pipeline création-de-repo + premier déploiement de la Phase D, avec un retour de progression en direct vers l'UI (SSE ou polling) car génération + premier déploiement prend un temps réel.
- C'est cette pièce qui rend littéralement vrai « juste mentionner le nom du projet, sélectionner les modules, fournir les infos GitHub, le domaine — création et déploiement instantanés ».

### Phase F — Refonte visuelle du dashboard
- Passe de design réelle sur `AdminLayout`, `FleetGrid` et les pages admin — une fois les Phases B–C ayant simplifié le modèle de données (plus de colonne tier, plus de compte à rebours de kill), les vues grille/détail deviennent plus simples à redessiner proprement. Périmètre : layout moderne, thème clair/sombre, cartes de projet avec statut/santé en direct, l'UI de l'assistant (Phase E), et un fil d'activité/sécurité consolidé puisant dans `security_events` + `fleet_lifecycle_events` + l'historique des webhooks de déploiement.

## Note de séquencement

Les phases A → B → C sont le socle nécessaire (elles touchent la même surface couplée aux tiers et doivent avancer ensemble, avec le livre mis à jour en parallèle du code selon la règle de `CLAUDE.md`). Les phases D, E, F sont additives par-dessus et peuvent être séquencées indépendamment une fois le socle fusionné et sa suite de tests au vert. **Ce document ne met en œuvre aucune de ces phases** — c'est la feuille de route à examiner et valider, phase par phase, lors de prochaines sessions.

## Approche de vérification (pour le moment où l'implémentation démarrera)

- **Phase A** : pas de vérification automatisée (documentation) ; confirmer manuellement qu'aucun chapitre n'affirme encore un fait contredit par la nouvelle architecture, et que les références croisées (numéros de chapitre/ancres) résolvent toujours.
- **Phase B/C** : `python -m pytest src/tests` doit passer après suppression de la logique de tier de chaque fichier — selon `CLAUDE.md`, on corrige le code (pas les tests) en cas d'échec, et on ne touche aux assertions d'un test que si son *intention* était vraiment spécifique aux tiers (le test lui-même n'a plus de sens, pas seulement qu'il échoue).
- **Phase D** : un test d'intégration contre un repo GitHub jetable/sandbox (créer → push → déclenchement du webhook → exécution du pipeline de déploiement) avant de faire confiance au flux contre un vrai repo opérateur ; la vérification de signature de webhook reçoit son propre test unitaire (sur le modèle déjà existant de `test_fleet_register_token.py`/`test_collector_stats_token.py` pour l'auth machine-à-machine).
- **Phase E** : un test de bout en bout qui pilote l'endpoint backend de l'assistant avec une sélection de modules factice et vérifie qu'un vrai dossier de projet + `docker-compose.yml` + repo git en ressortent (extension du pattern déjà existant de `test_generator_spike.py`).
- **Phase F** : pas de nouveau risque backend ; revue visuelle + suite Vitest frontend existante (`npm test`) qui reste au vert.
