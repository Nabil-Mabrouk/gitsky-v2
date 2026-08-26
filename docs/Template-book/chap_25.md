# Guide de l'Opérateur : Utiliser, Déployer, Maintenir GitSky

Les chapitres précédents ont construit chaque brique de GitSky. Celui-ci les
réunit en un **parcours opérateur** de bout en bout : de la première connexion au
VPS jusqu'à la routine matinale sur une flotte de dizaines de projets. C'est le
chapitre à garder ouvert le jour où l'on passe à l'action.

Trois temps, dans cet ordre :

1. **Utiliser** — créer un projet à partir d'un besoin.
2. **Déployer** — le mettre en ligne sur le VPS partagé, puis le laisser se redéployer tout seul à chaque évolution.
3. **Maintenir** — le garder (et toute la flotte) en bonne santé.

---

## 1. Utiliser : du besoin au projet

### 1.1 Préparer le VPS (une seule fois)

Avant le premier projet, le serveur partagé est provisionné **une fois** (Chap 22) :
durcissement SSH par clé, pare-feu UFW, Fail2ban, installation de Docker, puis
démarrage des services partagés — Traefik (seul exposé), l'instance PostgreSQL
des services, le landing collector optionnel, le LLM proxy, le GeoIP (Chap 18).

```bash
# Sur le VPS, une fois : bootstrap des services partagés (Chap 18/22).
cd /opt/gitsky/shared_services
docker compose up -d
```

### 1.2 Créer un projet via l'assistant du dashboard

Le chemin recommandé passe par l'**assistant de création** (Chap 27), accessible
depuis le fleet dashboard : nom du projet, sélection des modules dans le
catalogue (Chap 2), domaine, et informations GitHub (créer un nouveau dépôt ou
lier un dépôt existant — Chap 26). Un clic sur « Créer & Déployer » déclenche la
génération, la création du dépôt, le premier déploiement, et l'enregistrement au
fleet dashboard.

### 1.3 Alternative : décrire le projet dans un `config.yaml`

Pour scripter la création de plusieurs projets, ou en dehors du dashboard, le
générateur reste utilisable directement en ligne de commande (Chap 17) :

```yaml
# projects/mon-projet.yaml
project:
  name: mon-projet
  domain: mon-projet.mystudio.com
modules:
  admin: true
  analytics: true
branding:
  primary_color: "#4F46E5"
```

```bash
copier copy \
    --data-file projects/mon-projet.yaml \
    https://github.com/mystudio/gitsky-template \
    ~/projects/mon-projet
```

Le générateur résout les flags de modules, scaffolde `app/domain/`, génère les
migrations, applique le branding, produit le `docker-compose.yml` et le `.env`
(avec des **secrets aléatoires par projet** — `SECRET_KEY`, mot de passe
PostgreSQL), enregistre le projet au fleet dashboard, et crée le commit initial.
Le `.env.backup.example` est pré-rempli avec les noms réels du projet pour la
maintenance (Chap 23).

Pour créer plusieurs projets d'un coup, on écrit plusieurs YAML et on boucle
(Chap 17 §Bootstrapping d'une Flotte) — mais l'assistant (§1.2) reste le chemin
le plus rapide pour un usage courant, un projet à la fois.

---

## 2. Déployer : du projet à la mise en ligne continue

### 2.1 Le modèle de déploiement

Un projet généré est **auto-suffisant** : son `docker-compose.yml` de production
décrit tout ce dont il a besoin — frontend, backend, **son propre conteneur
PostgreSQL**, et un service `migrate` éphémère, sans exception. Le conteneur DB
reste sur le réseau interne, jamais exposé (Chap 23 §2.3).

Une seule image de production par service, identique quels que soient les
modules activés : ce sont les flags `MODULE_*` du `.env` qui décident, au
démarrage, quels routers et migrations se chargent. Le nombre de workers
Gunicorn vient de `WEB_CONCURRENCY`, une simple valeur de configuration par
projet — l'ajuster ne demande qu'un redéploiement, **sans rebuild** (Chap 21).

### 2.2 Premier déploiement

Que le projet vienne de l'assistant (§1.2) ou du générateur en ligne de
commande (§1.3), le premier déploiement suit la même mécanique :

```bash
# Sur le VPS, dans le dossier du projet.
cd /opt/gitsky/projects/mon-projet
docker compose up -d --build
```

Compose builde les images, crée la base du projet, applique les migrations via
le service `migrate`, puis démarre backend et frontend. Traefik détecte les
labels du projet et route `mon-projet.mystudio.com` (frontend) et
`api.mon-projet.mystudio.com` (backend) avec un certificat SSL wildcard
automatique (Chap 22).

### 2.3 Déploiement continu via GitHub

Une fois le premier déploiement effectué, chaque `git push` sur la branche par
défaut du dépôt du projet redéploie automatiquement (Chap 26) : le webhook du
fleet dashboard reçoit la notification, tire les dernières modifications,
reconstruit et redémarre les conteneurs, applique les migrations, et vérifie la
santé du projet. Pour un dépôt existant sans webhook configuré, un bouton
« Redéployer » dans le fleet dashboard rejoue la même séquence à la demande.

### 2.4 Vérifier le déploiement

L'endpoint `/health` sonde la base (`SELECT 1`) et renvoie `503` si elle est
injoignable — le `HEALTHCHECK` Docker s'en sert, et Traefik n'envoie du trafic
qu'à un conteneur sain (Chap 21/23) :

```bash
curl https://api.mon-projet.mystudio.com/api/health
# {"status":"ok","database":"ok","modules":["auth","admin","analytics"]}
```

Le projet apparaît alors dans le fleet dashboard, où l'opérateur suit son statut
sans SSH (Chap 19).

---

## 3. Maintenir : garder la flotte en bonne santé

La maintenance n'est pas optionnelle : c'est ce qui distingue une démo d'une
plateforme fiable (Chap 23). Sur une flotte, elle est **mutualisée** — un seul
jeu de crons pour tous les projets, piloté depuis le VPS.

### 3.1 Les trois piliers (dès le premier jour)

1. **Sauvegardes automatiques** — sans elles, tout le reste est inutile.
2. **Monitoring de disponibilité** — savoir avant les utilisateurs.
3. **Alerte disque** — le disque plein est la panne la plus courante et évitable.

### 3.2 L'automatique : `crontab.fleet`

Un unique crontab (`shared_services/crontab.fleet`, Chap 23 §6) orchestre toute
la flotte :

| Fréquence | Tâche | Script |
|---|---|---|
| 60 s | Poll `/health` de la flotte → alerte `deployment_failed` | `fleet-health.sh` |
| 02:00 | Sauvegarde 3-2-1 de toutes les bases projet | `backup-fleet.sh` |
| Horaire | Jauge disque consolidée | `fleet-disk.sh` |

Chaque conteneur DB étant isolé (Chap 18 §2), `backup-fleet.sh` boucle sur les
conteneurs `*_db` et en dump un par un — aucune exception, tout projet en a un.

### 3.3 Le manuel : la routine

Les tâches qui demandent un œil humain sont regroupées dans le calendrier de
maintenance (`shared_services/MAINTENANCE.md`, Chap 23 §6) :

- **Hebdo** — revue des erreurs 5xx et des `security_events` suspects ; vérifier
  que la dernière sauvegarde de flotte existe ; passer en revue les projets
  candidats à l'archivage sur le fleet dashboard (Chap 19/20).
- **Mensuel** — **tester une restauration** au hasard (une sauvegarde jamais
  restaurée est inutile), analyse santé DB (`db_health.sql`), scan CVE des
  dépendances.
- **Semestriel** — rotation des `SECRET_KEY` et mots de passe DB.

### 3.4 Mettre à jour toute la flotte

Un correctif du template se propage par `copier update` — chaque projet rejoue
ses migrations et reçoit les évolutions du châssis, sans perdre sa vitrine
art-dirigée (Chap 17 §Mise à Jour, Chap 24) :

```bash
cd /opt/gitsky/projects/mon-projet
copier update           # applique les nouveautés du template
docker compose up -d --build
```

Les images de base se rafraîchissent via `update_images.sh` (Chap 23 §5), qui
épingle des versions **supportées** (Node LTS active, etc.).

### 3.5 En cas d'incident

Un runbook incident (Chap 23 §7) couvre la restauration d'urgence
(`emergency_restore.sh`, qui préserve l'ancienne base sous `{db}_old`) et la
checklist post-incident (isoler, rotater tous les secrets, analyser les logs,
notifier sous 72 h si données personnelles — RGPD).

### 3.6 Archiver un projet

Quand un projet n'a plus vocation à tourner, l'opérateur l'archive manuellement
depuis le fleet dashboard (Chap 19/20) — jamais par un `docker compose down`
ad hoc, sinon la sauvegarde froide et la journalisation ne se font pas.

---

## Le cycle complet, en une image

```text
   BESOIN
    │  config.yaml ou assistant (Chap 27)
    ▼
  UTILISER ── création + dépôt GitHub ──► projet démarrable, enregistré au dashboard
    │                                        (Chap 17/26/27)
    ▼
  DÉPLOYER ── premier déploiement, puis push GitHub ──► en ligne derrière Traefik, /health vert
    │                                        (Chap 21/22/26)
    ▼
  MAINTENIR ── crontab.fleet ──► sauvegardes, monitoring, mises à jour
    │                                        (Chap 23)
    ▼
  DÉCISION OPÉRATEUR ──► ajuster les modules, changer de domaine, ou archiver
                                             (Chap 2/19/20)
```

C'est cette boucle — répétée sur des dizaines de projets, avec la même
discipline de maintenance pour tous — qui transforme GitSky d'un template en un
véritable **framework d'hébergement de flotte**.
