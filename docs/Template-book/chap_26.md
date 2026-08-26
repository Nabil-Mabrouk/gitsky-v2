# Intégration GitHub & Déploiement Automatique

## Introduction

Un projet généré n'est qu'un point de départ (Chap 17) : la logique métier qui le rend utile se construit ensuite, dans un dépôt Git, comme n'importe quel projet FastAPI/React. Ce chapitre décrit comment GitSky relie le cycle de vie d'un dépôt GitHub à celui d'un déploiement — de la création automatique du dépôt jusqu'au redéploiement déclenché par un simple `git push`.

> **État d'implémentation.** Ce chapitre documente la conception cible de cette intégration (feuille de route, phase D). Comme les tâches `_tasks` du générateur au Chap 17 (encore marquées « SIMULÉ » pour `provision_db`/`register_fleet`), la création de dépôt et le récepteur de webhook décrits ici sont à connecter à la vraie API GitHub — ce chapitre sert de spécification à cette implémentation, pas d'documentation d'un système déjà en production.

## 1. Pourquoi une GitHub App, Pas un Token Personnel

GitSky s'appuie sur une **GitHub App** installée une fois par l'opérateur sur son compte ou son organisation GitHub, plutôt que sur un jeton d'accès personnel (PAT) collé dans un fichier `.env`. Trois raisons :

- **Portée limitée** : une GitHub App ne reçoit que les permissions qu'elle déclare (création de dépôt, lecture/écriture du contenu, gestion des webhooks) — jamais l'accès complet d'un compte personnel.
- **Révocable sans casser un compte utilisateur** : désinstaller l'App coupe l'accès net, sans avoir à faire tourner le mot de passe ou les jetons personnels de l'opérateur.
- **Pas de secret longue-durée dans `.env`** : l'App s'authentifie avec une clé privée détenue uniquement par le fleet dashboard (service partagé, Chap 18), jamais copiée dans un projet individuel.

L'installation de la GitHub App (identifiant d'installation + clé privée) est un secret de **service partagé**, au même titre que la clé API du LLM proxy — jamais dupliqué par projet.

## 2. Deux Chemins de Création

L'assistant de création (Chap 27) propose les deux à l'opérateur.

### 2.1 Créer un Nouveau Dépôt

La `_task` du générateur (Chap 17) qui gère GitHub, exécutée après la génération des fichiers :

1. Crée un dépôt (privé par défaut) via l'API GitHub, nommé d'après le projet.
2. Pousse le commit initial généré par Copier.
3. Installe le webhook (`push` events) pointant vers le fleet dashboard.
4. Enregistre l'URL du dépôt sur l'entrée du projet dans le fleet dashboard.

### 2.2 Lier un Dépôt Existant

Pour un projet dont le code vit déjà ailleurs, l'opérateur fournit l'URL du dépôt existant. Deux cas :

- **La GitHub App est installée sur ce dépôt** (l'opérateur l'a autorisée) : le dashboard installe le webhook comme au §2.1, le déploiement continu fonctionne à l'identique.
- **La GitHub App n'a pas accès à ce dépôt** : le dashboard renonce à installer le webhook. Le projet reste géré, mais son redéploiement passe par le bouton manuel du dashboard (Chap 19, Chap 25 §2.3) plutôt que par un `push` automatique.

## 3. Le Pipeline de Déploiement

Un nouvel endpoint reçoit les notifications GitHub :

```
POST /api/fleet/webhooks/github/{project}
```

### 3.1 Vérification de la Signature

GitHub signe chaque requête webhook avec un secret propre au dépôt (HMAC-SHA256, en-tête `X-Hub-Signature-256`). Même doctrine que les autres gardes machine-à-machine du chassis (`X-Fleet-Token`, `X-Collector-Token` — Chap 18/19) : comparaison à temps constant, `503` fail-closed si le secret n'est pas configuré en production.

```python
# app/modules/fleet/github_webhook.py — cible
import hmac, hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### 3.2 Séquence de Déploiement

Sur un événement `push` vers la branche par défaut du dépôt :

1. `git fetch` puis `git reset --hard origin/<branche>` dans le dossier du projet sur le VPS — jamais un `git pull` brut, pour garantir un état reproductible même en cas d'historique réécrit.
2. Si le template a évolué depuis la génération : `copier update --defaults`.
3. `docker compose up -d --build` — reconstruit uniquement ce qui a changé.
4. Le service `migrate` applique les migrations en attente.
5. Un contrôle de santé (`GET /health`) confirme le succès.
6. Le résultat (succès ou échec, avec le SHA du commit déployé) est journalisé dans `fleet_lifecycle_events`, visible depuis le dashboard (Chap 19).

Un événement sur une autre branche que la branche par défaut est ignoré — seule la branche par défaut du dépôt déclenche un déploiement.

### 3.3 Échec de Déploiement

Un échec à n'importe quelle étape (build, migration, health check) :

- N'interrompt pas le projet déjà en ligne — les conteneurs existants continuent de tourner jusqu'à ce que la nouvelle version soit prête.
- Déclenche l'alerte `webhook_deploy_failed` (Chap 19).
- Laisse le dernier déploiement réussi comme référence pour un nouvel essai (`git reset --hard` reproduira le même état au prochain push, ou au clic sur « Redéployer »).

## 4. Sécurité

- Le secret du webhook est propre à chaque projet (`GITHUB_WEBHOOK_SECRET` dans son `.env`), jamais partagé entre projets — un secret compromis n'affecte qu'un seul déploiement.
- Le webhook n'exécute jamais de code arbitraire issu du payload GitHub — seulement la séquence fixe du §3.2, sur le dépôt et la branche attendus.
- Le secret du webhook suit le même calendrier de rotation que les autres secrets projet (Chap 23 §2.2) — rotation en cas de compromission suspectée.
- La clé privée de la GitHub App (service partagé) est stockée hors du VCS, au même titre que les autres secrets de `shared_services` (Chap 18).

## 5. Repli Manuel

Quand le webhook n'est pas installable (dépôt existant sans accès App) ou temporairement en panne, le bouton « Redéployer » du fleet dashboard (Chap 19) exécute exactement la même séquence (§3.2) de façon synchrone, à la demande de l'opérateur. Aucune fonctionnalité de déploiement n'est donc strictement dépendante du webhook — c'est un raccourci d'automatisation, pas un chemin unique.

## Anti-Patterns à Éviter

- **Faire confiance au payload webhook sans vérifier la signature.** N'importe qui connaissant l'URL de l'endpoint pourrait déclencher un redéploiement arbitraire.
- **Utiliser un jeton personnel partagé entre plusieurs projets.** Une fuite compromet toute la flotte plutôt qu'un seul dépôt.
- **Déployer sur un push vers n'importe quelle branche.** Seule la branche par défaut doit déclencher un déploiement en production.

## Checklist du Chapitre

- [ ] Je comprends pourquoi une GitHub App remplace un token personnel
- [ ] Je sais distinguer le chemin « nouveau dépôt » du chemin « dépôt existant »
- [ ] Je sais que le webhook n'est qu'un raccourci — le bouton manuel fait toujours le même travail
- [ ] Je vérifie que la signature du webhook est validée avant tout traitement

---

*L'intégration GitHub ferme la boucle entre création et déploiement continu. Le prochain chapitre décrit l'assistant de création qui assemble tout ce que les Chap 2, 17 et 26 ont posé — modules, GitHub, domaine — en un seul parcours pour l'opérateur.*
