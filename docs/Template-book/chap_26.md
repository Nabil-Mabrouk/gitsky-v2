# Intégration GitHub et Déploiement Continu

## Introduction

Chaque projet généré vit dans son propre dépôt GitHub (Chap 17). Jusqu'ici, faire évoluer le code déployé signifiait se connecter au VPS et lancer `git pull && docker compose up -d --build` à la main — fiable, mais entièrement manuel. Ce chapitre couvre ce qui a été construit pour automatiser cette boucle : la création d'un dépôt (ou le lien vers un dépôt existant) et l'installation de son webhook depuis le dashboard, la réception sécurisée des livraisons GitHub, et le pipeline de redeploy automatique — et **le dit aussi clairement là où ce n'est pas encore fait** : le premier push du code généré vers le dépôt fraîchement créé reste, à ce stade, une étape manuelle.

> Ce chapitre documente un état en construction (Phase 6, incrément GitHub). La création/liaison de dépôt, l'installation du webhook, la réception sécurisée et le pipeline de redeploy sont réels et testés. Le premier push automatique du code généré existe aussi désormais — mais seulement dans le chemin du wizard de création (Chap 27) ; appelés seuls sur un projet déjà généré, `create-repo`/`link-repo` ne poussent toujours rien (voir « Ce qui Manque Encore »).

## Ce qui Fonctionne Aujourd'hui

### Créer ou Lier un Dépôt

Depuis l'onglet Actions d'un projet (Chap 19), l'opérateur dispose de deux chemins :

- **`POST /api/fleet/projects/{name}/github/create-repo`** — crée un nouveau dépôt via l'API GitHub (`FLEET_GITHUB_ORG` si configuré, sinon le compte propriétaire du jeton), puis tente d'y installer le webhook push.
- **`POST /api/fleet/projects/{name}/github/link-repo`** — le repli manuel : lie un dépôt **déjà existant** (`owner/repo`) sans passer par la création, puis tente lui aussi d'installer le webhook. Utile quand le code vit déjà dans un dépôt avant d'entrer dans la flotte (import, dépôt créé à la main).

Dans les deux cas, un échec d'installation du webhook (le jeton n'a pas les droits admin sur ce dépôt — cas fréquent pour un dépôt tiers lié manuellement) **ne fait jamais échouer la requête** : le dépôt reste lié, `github_webhook_installed` passe à `false`, et un message explique le repli — le redeploy reste alors disponible en manuel (`git pull` + `docker compose up -d --build` à la main sur le VPS, ou en relançant le lien une fois les droits corrigés). Le dashboard affiche cet état sur la fiche projet, jamais de faux positif silencieux.

**Ce que ces deux endpoints ne font pas encore : pousser le code.** Créer ou lier le dépôt n'y met rien — le premier push du projet généré (Chap 17) vers ce dépôt, puis le premier `git clone` sur le VPS, restent une étape manuelle de l'opérateur. Le webhook et le poller ne prennent le relais qu'une fois cette étape initiale faite.

Authentification : un jeton d'accès personnel (`FLEET_GITHUB_TOKEN`) plutôt qu'une GitHub App complète — un choix pragmatique pour cette itération (Cf. Ce qui Manque Encore).

### Le Webhook

`POST /api/fleet/webhooks/github/{name}` reçoit les livraisons GitHub configurées sur le dépôt d'un projet (événement `push`). Deux vérifications avant de journaliser quoi que ce soit :

1. **Signature HMAC-SHA256** — GitHub signe chaque livraison avec un secret partagé (`FLEET_GITHUB_WEBHOOK_SECRET`), transmis dans l'en-tête `X-Hub-Signature-256: sha256=<hmac>`. Une signature absente ou fausse vaut un `401` — même garde fail-open-dev/fail-closed-prod que le token M2M de `/register` (Chap 19) : secret non configuré, ouvert en dev ; secret non configuré en production, `503`.
2. **Branche de déploiement** — un push est un signal de déploiement uniquement s'il atterrit sur `FLEET_GITHUB_DEPLOY_BRANCH` (défaut `main`). Un push sur une branche feature ou WIP est reçu et vérifié, mais ne déclenche rien : le développeur n'a pas fini, il n'a pas mergé.

Un push qui passe les deux vérifications journalise un événement `deploy_triggered` dans `fleet_lifecycle_events` (Chap 20). Le webhook ne fait **que ça** — il ne touche à aucun conteneur, ne lance aucune commande shell. C'est un choix d'architecture délibéré (section suivante).

### Pourquoi le Conteneur Dashboard n'a Aucun Accès Docker

Exécuter réellement un `git pull` et un `docker compose up -d --build` demande un accès direct à Docker sur l'hôte. Deux options existaient :

- **Monter le socket Docker dans le conteneur dashboard.** Rapide, mais transforme le seul conteneur exposé publiquement de la flotte en équivalent root sur la machine hôte — un compromis de ce conteneur devient un compromis de tout le VPS, tous projets confondus.
- **Un script séparé, exécuté sur l'hôte, qui interroge le dashboard.** Plus de latence (quelques minutes au pire), mais le conteneur public-facing ne gagne aucun privilège supplémentaire.

Le second choix a été retenu. Le webhook journalise ; un script `shared_services` tournant en cron sur l'hôte exécute.

### Le Poller : `deploy-on-push.sh`

`shared_services/scripts/deploy-on-push.sh` tourne toutes les 2 minutes (`crontab.fleet`). Il interroge `GET /api/fleet/deploys/pending` — même garde M2M que `/register` et `/maintenance/report` — qui répond en **texte brut**, une ligne `<id>\t<nom_projet>` par événement `deploy_triggered` non encore traité. Texte brut plutôt que JSON parce que le seul consommateur est ce script shell, sans dépendance `jq` — cohérent avec le reste de `shared_services/scripts/`, qui construit du JSON en chaîne mais n'en parse jamais.

Le script tient son propre curseur local (`STATE_FILE`, `since_id`) : chaque événement n'est traité qu'une fois, même si le script tourne en boucle indéfiniment.

Pour chaque projet en attente :

```text
git pull --ff-only
  └─ (optionnel, RUN_COPIER_UPDATE=1) copier update --trust --defaults
docker compose up -d --build
  └─ vérification /health du conteneur backend
      └─ reporting vers /api/fleet/maintenance/report (job="deploy")
```

`git pull --ff-only` refuse tout merge ou rebase automatique — un historique divergent doit faire échouer le script bruyamment, pas être résolu en silence (règle déjà en place pour le dépôt du template lui-même : le serveur ne fait jamais que `pull`, Chap 22). `copier update` reste désactivé par défaut : il peut demander une résolution de conflit interactive, ce qui n'est pas sûr sans supervision sous cron — un projet qui a besoin d'absorber une évolution du template le fait pour l'instant à la main.

Un projet dont le répertoire est introuvable, dont le `git pull` échoue, ou dont le `/health` post-build ne répond pas, journalise un échec via `/api/fleet/maintenance/report` — visible dans l'onglet Maintenance du dashboard (Chap 19) au même titre qu'un échec de sauvegarde. Le curseur avance malgré l'échec : un projet cassé ne doit jamais bloquer indéfiniment les déploiements des projets suivants dans la file.

## Configuration

Variables d'environnement du backend (`.env` du fleet dashboard) :

| Variable | Rôle | Défaut |
|---|---|---|
| `FLEET_GITHUB_WEBHOOK_SECRET` | Secret HMAC partagé avec GitHub (réglage du webhook côté dépôt) | vide (dev ouvert, `503` en prod) |
| `FLEET_GITHUB_DEPLOY_BRANCH` | Branche dont un push déclenche un déploiement | `main` |
| `FLEET_GITHUB_TOKEN` | Jeton d'accès personnel utilisé pour créer des dépôts et installer des webhooks | vide (stub dev déterministe, `RuntimeError` en prod) |
| `FLEET_GITHUB_ORG` | Organisation GitHub sous laquelle créer les dépôts (`create-repo`) ; vide = compte propriétaire du jeton | vide |
| `FLEET_GITHUB_API_BASE` | Base de l'API GitHub (utile pour pointer vers un serveur de test) | `https://api.github.com` |

Quand `create-repo` ou `link-repo` installe le webhook automatiquement, il pointe vers `<site_url>/api/fleet/webhooks/github/<nom-projet>` avec le secret `FLEET_GITHUB_WEBHOOK_SECRET` — pas de saisie manuelle des réglages du webhook dans ce cas. Si l'installation échoue (droits insuffisants sur le dépôt), le recours reste la configuration manuelle côté GitHub (Settings → Webhooks → Add webhook du dépôt : URL `https://<dashboard>/api/fleet/webhooks/github/<nom-projet>`, content type `application/json`, secret identique à `FLEET_GITHUB_WEBHOOK_SECRET`, événement `push` uniquement).

Variables du poller (`crontab.fleet`, en plus de `FLEET_URL`/`FLEET_REGISTER_TOKEN` déjà utilisées par `fleet-health.sh` et `backup-fleet.sh`, Chap 23) :

| Variable | Rôle | Défaut |
|---|---|---|
| `PROJECTS_DIR` | Racine des projets déployés sur le VPS | `/opt/gitsky/projects` |
| `STATE_FILE` | Curseur local du poller | `/var/lib/gitsky/deploy-on-push.state` |
| `RUN_COPIER_UPDATE` | `1` pour lancer `copier update --trust` avant le build | désactivé |

## Ce qui Manque Encore

1. **`create-repo` et `link-repo`, appelés seuls sur la fiche d'un projet déjà généré, ne poussent toujours aucun code.** Ils s'occupent du dépôt et du webhook, pas du contenu — pousser le code existant vers le dépôt fraîchement créé/lié reste une étape manuelle de l'opérateur dans ce chemin-là. Le wizard de création (Chap 27) résout ce problème **pour un nouveau projet créé de zéro** : génération et premier push y sont orchestrés ensemble. Ce n'est donc plus une lacune universelle, mais une lacune propre au chemin « je gère GitHub après coup, sur un projet qui existe déjà ».
2. **Migration vers une GitHub App.** L'authentification actuelle (`FLEET_GITHUB_TOKEN`, un jeton d'accès personnel) est un choix pragmatique, pas la cible finale : un jeton à l'échelle du compte/org à révoquer manuellement, plutôt qu'une installation scopée et révocable par dépôt. Une GitHub App reste une amélioration documentée, pas un prérequis de cette phase — et le wizard (Chap 27) en hérite telle quelle.

## Checklist du Chapitre

- [ ] Je sais créer un nouveau dépôt (`create-repo`) ou lier un dépôt existant (`link-repo`) depuis l'onglet Actions d'un projet
- [ ] Je vérifie `github_webhook_installed` après coup — un échec d'installation ne bloque pas la liaison, mais laisse le redeploy automatique indisponible tant qu'il n'est pas corrigé
- [ ] `FLEET_GITHUB_TOKEN` est configuré en production (sinon `RuntimeError` fail-closed, par design) ; `FLEET_GITHUB_WEBHOOK_SECRET` l'est aussi (sinon `503` sur le webhook)
- [ ] Je sais que seule la branche `FLEET_GITHUB_DEPLOY_BRANCH` (défaut `main`) déclenche un déploiement
- [ ] `deploy-on-push.sh` tourne bien dans `crontab.fleet` et ses échecs remontent dans l'onglet Maintenance
- [ ] Je sais que `create-repo`/`link-repo`, appelés seuls sur un projet déjà généré, ne poussent aucun code — je ne présume pas qu'un bouton pousse le code avant de l'avoir vérifié. Pour un nouveau projet, le wizard (Chap 27) s'en charge.

---

*Ce chapitre clôt le socle GitHub : dépôt, webhook, réception sécurisée, pipeline de redeploy. Le chapitre suivant (Chap 27) assemble ces briques — plus le générateur (Chap 17) — derrière un seul geste opérateur : créer un projet de zéro.*
