# Guide de l'Opérateur : Utiliser, Déployer, Maintenir GitSky

Les chapitres précédents ont construit chaque brique de GitSky. Celui-ci les
réunit en un **parcours opérateur** de bout en bout : de la première connexion au
VPS jusqu'à la routine matinale sur une flotte de dizaines de projets. C'est le
chapitre à garder ouvert le jour où l'on passe à l'action.

Trois temps, dans cet ordre :

1. **Utiliser** — générer un projet à partir d'une idée.
2. **Déployer** — le mettre en ligne sur le VPS partagé.
3. **Maintenir** — le garder (et toute la flotte) en bonne santé.

---

## 1. Utiliser : de l'idée au projet

### 1.1 Préparer le VPS (une seule fois)

Avant le premier projet, le serveur partagé est provisionné **une fois** (Chap 22) :
durcissement SSH par clé, pare-feu UFW, Fail2ban, installation de Docker, puis
démarrage des services partagés — Traefik (seul exposé), l'instance PostgreSQL
des services, le landing collector, le LLM proxy, le GeoIP (Chap 18).

```bash
# Sur le VPS, une fois : bootstrap des services partagés (Chap 18/22).
cd /opt/gitsky/shared_services
docker compose up -d
```

### 1.2 Décrire l'idée dans un `config.yaml`

Chaque projet naît d'un fichier de configuration déclaratif (Chap 17). Le tier de
départ est **toujours T0** — un projet gagne ses tiers par signal mesurable, il ne
démarre jamais au niveau final (Chap 2) :

```yaml
# projects/pain-scraper.yaml
project:
  name: pain-scraper
  tier: t0
  domain: pain-scraper.mystudio.com
branding:
  primary_color: "#4F46E5"
landing:
  skin: clean
  blocks:
    - type: hero
      headline: "Trouvez la douleur avant d'écrire le code"
    - type: email_capture
      cta: "Rejoindre la liste"
```

### 1.3 Générer le projet

Une commande produit un projet démarrable (Chap 17) :

```bash
copier copy \
    --data-file projects/pain-scraper.yaml \
    https://github.com/mystudio/gitsky-template \
    ~/projects/pain-scraper
```

Le générateur résout le tier en flags de modules, scaffolde `app/domain/`, génère
les migrations, applique le branding, produit le `docker-compose.yml` et le
`.env` (avec des **secrets aléatoires par projet** — `SECRET_KEY`, mot de passe
PostgreSQL), enregistre le projet au fleet dashboard, et crée le commit initial.
Le `.env.backup.example` est pré-rempli avec les noms réels du projet pour la
maintenance (Chap 23).

Pour tester dix idées, on écrit dix YAML et on boucle — *zero-to-N* projets en
quelques minutes (Chap 17 §Bootstrapping d'une Flotte).

---

## 2. Déployer : du projet à la mise en ligne

### 2.1 Le modèle de déploiement

Un projet généré est **auto-suffisant** : son `docker-compose.yml` de production
décrit tout ce dont il a besoin. Selon le tier (Chap 21) :

- **T0** — frontend (landing statique art-dirigée, Chap 24) + backend minimal.
  Pas de base propre : les leads vont au landing collector partagé (Chap 18 §3).
- **T1 / T2** — frontend + backend + **son propre conteneur PostgreSQL** +
  service `migrate` éphémère. Le conteneur DB reste sur le réseau interne, jamais
  exposé (Chap 23 §2.3).

Une seule image de production par service, identique pour les trois tiers : ce
sont les flags `MODULE_*` du `.env` qui décident, au démarrage, quels routers et
migrations se chargent. Le nombre de workers Gunicorn vient de `WEB_CONCURRENCY`
(1/2/4 selon le tier) — promouvoir T1 → T2 = changer cette valeur et redéployer,
**sans rebuild** (Chap 21).

### 2.2 Déployer un projet

```bash
# Sur le VPS, dans le dossier du projet.
cd /opt/gitsky/projects/pain-scraper
# .env généré à la création : contient tier, secrets, WEB_CONCURRENCY.
docker compose up -d --build
```

Compose builde les images, crée la base du projet (T1/T2), applique les
migrations via le service `migrate`, puis démarre backend et frontend. Traefik
détecte les labels du projet et route `pain-scraper.mystudio.com` (frontend) et
`api.pain-scraper.mystudio.com` (backend) avec un certificat SSL wildcard
automatique (Chap 22).

### 2.3 Vérifier le déploiement

L'endpoint `/health` sonde la base (`SELECT 1`) et renvoie `503` si elle est
injoignable — le `HEALTHCHECK` Docker s'en sert, et Traefik n'envoie du trafic
qu'à un conteneur sain (Chap 21/23) :

```bash
curl https://api.pain-scraper.mystudio.com/api/health
# {"status":"ok","database":"ok","tier":"t0",...}
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
| 03:00 | Kill check (déclenché par le dashboard, Chap 20) | — |
| Horaire | Jauge disque consolidée | `fleet-disk.sh` |

La sauvegarde de 02:00 précède **volontairement** le kill check de 03:00 : un
projet sur le point d'être tué garde une sauvegarde fraîche. Chaque conteneur DB
étant isolé (Chap 18 §2), `backup-fleet.sh` boucle sur les conteneurs `*_db` et
en dump un par un.

### 3.3 Le manuel : la routine

Les tâches qui demandent un œil humain sont regroupées dans le calendrier de
maintenance (`shared_services/MAINTENANCE.md`, Chap 23 §6) :

- **Hebdo** — revue des erreurs 5xx et des `security_events` suspects ; vérifier
  que la dernière sauvegarde de flotte existe.
- **Mensuel** — **tester une restauration** au hasard (une sauvegarde jamais
  restaurée est inutile), analyse santé DB (`db_health.sql`), scan CVE des
  dépendances.
- **Semestriel** — rotation des `SECRET_KEY` et mots de passe DB.

### 3.4 Mettre à jour toute la flotte

Un correctif du template se propage par `copier update` — chaque projet rejoue
ses migrations et reçoit les évolutions du châssis, sans perdre sa vitrine
art-dirigée (Chap 17 §Mise à Jour, Chap 24) :

```bash
cd /opt/gitsky/projects/pain-scraper
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

---

## Le cycle complet, en une image

```text
   IDÉE
    │  config.yaml (tier T0)
    ▼
  UTILISER ── create-gitsky-project ──► projet démarrable + enregistré au dashboard
    │                                        (Chap 17)
    ▼
  DÉPLOYER ── docker compose up -d ──► en ligne derrière Traefik, /health vert
    │                                        (Chap 21/22)
    ▼
  MAINTENIR ── crontab.fleet ──► sauvegardes, monitoring, kill check, updates
    │                                        (Chap 23)
    ▼
  SIGNAL ? ──► promotion T1/T2 (WEB_CONCURRENCY + .env)   ou   kill (archivé)
                                             (Chap 2/19/20)
```

C'est cette boucle — répétée sur des dizaines d'idées, avec discipline de
portefeuille — qui transforme GitSky d'un template en une **usine à hypothèses
de startup**.
