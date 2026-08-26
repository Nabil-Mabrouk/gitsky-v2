# L'Assistant de Création

## Introduction

Les deux chapitres précédents ont posé les briques séparément : le catalogue de modules (Chap 2), le générateur Copier (Chap 17), l'enregistrement fleet (Chap 19), l'intégration GitHub (Chap 26). Ce chapitre les assemble derrière un seul geste opérateur : nom du projet, modules à activer, domaine, et un choix GitHub (créer un dépôt, en lier un existant, ou rien pour l'instant) → un projet généré sur disque, enregistré dans la flotte, avec son dépôt lié et son premier push tenté automatiquement.

> Ce chapitre documente un état en construction (Phase 6, incrément wizard). L'orchestration backend (génération, enregistrement, dépôt, premier push, bootstrap du premier déploiement) est réelle et testée ; ce qui reste manuel ou simplifié est listé en fin de chapitre, pas caché.

## Ce qui Fonctionne Aujourd'hui

### `POST /api/fleet/projects`

Un seul endpoint orchestre tout, dans un ordre délibéré :

1. **Validation.** Le nom doit être un slug DNS-safe (minuscules, chiffres, tirets — il devient un nom de répertoire, un identifiant PostgreSQL et un sous-domaine). `github_mode=link` exige `github_repo`. Invalide → `400`, avant toute autre étape.
2. **Génération.** `generator_client.generate_project` invoque `copier.run_copy` réellement (pas `skip_tasks=True` comme dans les tests du générateur) : le projet est matérialisé sous `PROJECTS_DIR/<nom>`, et les `_tasks` de `copier.yml` s'exécutent pour de vrai — `git init`, `git add`, un premier commit (Chap 17). C'est la seule étape **sans filet** : si le générateur n'est pas accessible (`GITSKY_GENERATOR_PATH` absent ou invalide), la requête échoue en `503` et **rien n'est enregistré** — pas de projet fantôme dans la flotte.
3. **Enregistrement.** Une fois généré, le projet est inséré dans `fleet_projects` et journalise `born` (même geste que `/projects/register`, Chap 19) — le domaine par défaut est `<nom>.mystudio.com` si aucun n'est fourni (Chap 1).
4. **GitHub (optionnel).** Selon `github_mode` : `create` appelle `github_client.create_repo` (Chap 26) ; `link` utilise le `github_repo` fourni tel quel. Dans les deux cas, le webhook push est tenté (`_install_webhook`, la même fonction que les endpoints `create-repo`/`link-repo` de la fiche projet).
5. **Premier push.** Si un dépôt a été créé ou lié, `git_client.push_initial_commit` ajoute le remote et pousse le commit initial du projet généré.
6. **Bootstrap du premier déploiement.** Si le push a réussi mais que le webhook n'a **pas** pu être installé, rien d'autre ne déclenchera jamais de redeploy pour ce projet — le endpoint journalise lui-même un `deploy_triggered` pour que `deploy-on-push.sh` (Chap 26) le trouve au prochain passage. Si le webhook **est** installé, GitHub notifiera de lui-même à la prochaine livraison : pas de double déclenchement.

**À partir de l'étape 3, plus rien n'est fatal.** Un échec de création de dépôt, d'installation de webhook, ou de premier push ne fait jamais échouer la requête (toujours `201`) — il est journalisé sous forme de message dans `warnings`, et l'opérateur peut reprendre la main depuis la fiche projet (les endpoints `create-repo`/`link-repo` de Chap 26 restent utilisables après coup). Un projet généré et enregistré sans dépôt lié est un résultat utile, jamais une raison de tout annuler.

### `GET /api/fleet/module-catalog`

Renvoie le catalogue plat (Chap 2), clés courtes sans le préfixe `module_` — c'est ce que le formulaire affiche en cases à cocher. `auth` n'y figure pas : il est core, jamais un choix.

### L'Écran du Wizard

Un seul écran (`/admin/fleet/new`, accessible depuis le bouton « + Nouveau projet » de la grille, Chap 19), pas une suite d'étapes avec barre de progression : nom, cases à cocher pour les modules, domaine optionnel, et un choix GitHub (radio : aucun / créer / lier, avec le champ `owner/repo` qui n'apparaît que pour le lien). À la soumission, un résumé affiche ce qui a réellement été fait — projet généré, dépôt lié, webhook installé ou non, push réussi ou non, premier déploiement déclenché ou non — et les avertissements le cas échéant, jamais un faux « tout est vert » silencieux.

## Configuration

| Variable | Rôle | Défaut |
|---|---|---|
| `GITSKY_GENERATOR_PATH` | Chemin vers le dossier du générateur (contient `copier.yml`) | absent — la création de projet échoue en `503` sans lui |
| `PROJECTS_DIR` | Racine où les projets sont générés (même variable que `deploy-on-push.sh`, Chap 26) | `/opt/gitsky/projects` |

**Le paquet `copier` n'est pas dans `requirements.txt` du template**, par le même raisonnement que le SDK Stripe (Chap 16) : c'est une dépendance propre au module `fleet`, pas à tout projet généré — l'ajouter inconditionnellement gonflerait l'image de chaque projet pour une capacité que seul le fleet dashboard utilise. Une image de fleet dashboard doit l'installer en plus. L'import est paresseux (`import copier` à l'intérieur de la fonction, pas en tête de module) : un projet qui n'active pas `module_fleet` ne charge jamais ce code, et un fleet dashboard sans `copier` installé démarre quand même — la création de projet échoue seulement au moment où elle est tentée, pas au démarrage du process.

## Ce qui Manque Encore

1. **Pas de flux de progression (SSE/polling).** L'endpoint est synchrone : la requête HTTP reste ouverte le temps de la génération + de l'enregistrement + du dépôt + du push. Pour le template actuel (quelques dizaines de fichiers), ça reste de l'ordre de la seconde ; un template qui grossirait significativement, ou une génération sur un disque lent, justifierait de repasser ce flux en asynchrone avec suivi de progression (Chap 27, roadmap originale) — pas fait tant que le besoin ne s'est pas fait sentir.
2. **La provision de base de données réelle reste simulée.** `provision_db.py` (une des `_tasks` du générateur, Chap 17) ne crée une base que si `POSTGRES_CONTAINER` est configuré dans l'environnement du process qui génère — sinon il l'ignore proprement. Le wizard ne configure pas cette variable à la place de l'opérateur.
3. **Pas de vérification DNS.** Le domaine fourni (ou le sous-domaine par défaut) n'est jamais vérifié disponible ni câblé automatiquement côté Traefik — cette étape reste, comme avant ce chapitre, une action d'infra séparée.
4. **La migration GitHub App reste ouverte** (Chap 26) : le wizard hérite de la même authentification par jeton d'accès personnel que `create-repo`/`link-repo`.

## Checklist du Chapitre

- [ ] `GITSKY_GENERATOR_PATH` et `PROJECTS_DIR` sont configurés sur le fleet dashboard en production
- [ ] Le paquet `copier` est installé dans l'image du fleet dashboard (absent du `requirements.txt` de base, par design)
- [ ] Je sais lire un résultat de création : `generated`/`github_repo`/`webhook_installed`/`pushed`/`deploy_triggered` et la liste `warnings`
- [ ] Je sais qu'un warning n'est jamais une raison de relancer toute la création — les endpoints `create-repo`/`link-repo` (Chap 26) reprennent la main sur un projet déjà généré
- [ ] Je sais que la provision de base réelle et le câblage DNS restent hors périmètre de ce wizard

---

*Ce chapitre clôt la partie industrialisation : de l'idée d'un nouveau projet à son premier déploiement, en un seul geste opérateur, avec les limites de cette version assumées plutôt que cachées. Le prochain chantier ouvert — la refonte visuelle du dashboard (Phase F) — n'a pas sa place ici tant que le code ne la fait pas.*
