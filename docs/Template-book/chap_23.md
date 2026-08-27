# Maintenance en Production : Sécurité, Sauvegardes et Surveillance

## Pourquoi la Maintenance est Non-Négociable

Déployer une application en production n'est pas la fin du travail — c'est le début d'une responsabilité. Une plateforme sans maintenance est comme une voiture sans vidange : elle fonctionne parfaitement au départ, puis se dégrade silencieusement jusqu'à la panne catastrophique.

Pour le projet GitSky, quatre menaces pèsent sur vos données et votre disponibilité :

```text
┌─────────────────────────────────────────────────────────────────┐
│                    MENACES EN PRODUCTION                        │
├──────────────────┬──────────────────────┬───────────────────────┤
│ MENACE           │ EXEMPLE CONCRET       │ PROTECTION            │
├──────────────────┼──────────────────────┼───────────────────────┤
│ Perte de données │ Crash disque,         │ Sauvegardes           │
│                  │ DELETE accidentel     │ automatiques          │
├──────────────────┼──────────────────────┼───────────────────────┤
│ Corruption       │ Migration ratée,      │ Sauvegardes +         │
│                  │ panne matérielle      │ tests de restauration │
├──────────────────┼──────────────────────┼───────────────────────┤
│ Exposition       │ Fuite de credentials, │ Rotation des secrets  │
│                  │ injection SQL         │ + durcissement DB     │
├──────────────────┼──────────────────────┼───────────────────────┤
│ Dégradation      │ Disque plein,         │ Monitoring +          │
│                  │ requêtes lentes       │ maintenance planifiée │
└──────────────────┴──────────────────────┴───────────────────────┘
```

Ce chapitre vous donne les outils, les scripts, et le calendrier pour maintenir votre plateforme en bonne santé durablement.

---

## Partie 1 : Sauvegardes PostgreSQL

### La Règle du 3-2-1

Toute stratégie de sauvegarde professionnelle respecte cette règle fondamentale :

- **3** copies de vos données
- **2** sur des supports ou emplacements différents
- **1** copie hors site (S3, Backblaze, autre serveur)

Pour GitSky, cela se traduit par :
1. La base de données active sur votre serveur (copie 1)
2. Les dumps compressés sur le même serveur dans `/backups/` (copie 2)
3. Les dumps synchronisés vers un stockage cloud (copie 3, hors site)

### Types de Sauvegardes

**Dump logique (`pg_dump`)** : Exporte les données sous forme de SQL. Simple, portable, restaurable sur n'importe quelle instance PostgreSQL. Idéal pour les petites et moyennes bases (< 50 Go).

**Sauvegarde physique (`pg_basebackup`)** : Copie binaire des fichiers de données. Plus rapide pour les très grandes bases, nécessite la même version de PostgreSQL pour la restauration.

**WAL Archiving** (avancé) : Archive les journaux de transactions en continu, permettant une restauration à n'importe quel instant précis (Point-In-Time Recovery). Recommandé quand votre base contient des données financières critiques.

Pour GitSky, le **dump logique quotidien** est le point de départ adapté.

### Script de Sauvegarde Automatisé

Créez le fichier `scripts/backup_db.sh` à la racine de votre projet :

```bash
#!/usr/bin/env bash
# =============================================================================
# scripts/backup_db.sh
# Sauvegarde automatisée de la base PostgreSQL avec rotation et alerte.
#
# Usage : ./scripts/backup_db.sh
# Variables d'environnement requises (lues depuis .env.backup) :
#   POSTGRES_CONTAINER  — nom du conteneur Docker PostgreSQL
#   POSTGRES_DB         — nom de la base de données
#   POSTGRES_USER       — utilisateur PostgreSQL
#   BACKUP_DIR          — répertoire local de stockage
#   BACKUP_RETENTION    — nombre de jours de rétention (défaut: 14)
#   S3_BUCKET           — bucket S3 (optionnel)
#   ALERT_EMAIL         — email pour les alertes d'échec (optionnel)
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env.backup"

if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-gitsky_db}"
POSTGRES_DB="${POSTGRES_DB:-gitsky}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
BACKUP_RETENTION="${BACKUP_RETENTION:-14}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

# ── Fonctions utilitaires ──────────────────────────────────────────────────────
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

alert() {
    local message="$1"
    log "ERREUR: $message"
    if [[ -n "${ALERT_EMAIL:-}" ]]; then
        echo "$message" | mail -s "[GitSky] ALERTE: Échec sauvegarde DB" "$ALERT_EMAIL" 2>/dev/null || true
    fi
}

# ── Vérifications préalables ───────────────────────────────────────────────────
# Créer le répertoire AVANT le premier `log` : la fonction log() écrit dans
# $BACKUP_DIR/backup.log via tee, et avec `set -o pipefail` un tee vers un
# dossier inexistant fait échouer la toute première sauvegarde.
mkdir -p "$BACKUP_DIR"

log "=== Démarrage de la sauvegarde ==="

# Vérifier que le conteneur tourne
if ! docker inspect "$POSTGRES_CONTAINER" --format='{{.State.Status}}' 2>/dev/null | grep -q "running"; then
    alert "Le conteneur $POSTGRES_CONTAINER n'est pas en cours d'exécution."
    exit 1
fi

# ── Sauvegarde ────────────────────────────────────────────────────────────────
log "Dump de la base '$POSTGRES_DB' vers $BACKUP_FILE..."

if docker exec "$POSTGRES_CONTAINER" \
    pg_dump -U "$POSTGRES_USER" --format=plain --no-owner --no-acl "$POSTGRES_DB" \
    | gzip -9 > "$BACKUP_FILE"; then

    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    log "Sauvegarde réussie : $BACKUP_FILE ($SIZE)"
else
    alert "pg_dump a échoué pour la base '$POSTGRES_DB'."
    rm -f "$BACKUP_FILE"
    exit 1
fi

# ── Vérification d'intégrité ──────────────────────────────────────────────────
log "Vérification de l'intégrité du fichier..."
if ! gzip -t "$BACKUP_FILE"; then
    alert "Le fichier de sauvegarde est corrompu : $BACKUP_FILE"
    rm -f "$BACKUP_FILE"
    exit 1
fi
log "Intégrité OK."

# ── Upload S3 (optionnel) ─────────────────────────────────────────────────────
if [[ -n "${S3_BUCKET:-}" ]]; then
    log "Upload vers S3 : s3://${S3_BUCKET}/postgres-backups/..."
    if aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/postgres-backups/" \
        --storage-class STANDARD_IA; then
        log "Upload S3 réussi."
    else
        alert "L'upload S3 a échoué. La sauvegarde locale est conservée."
        # On ne quitte pas en erreur : la sauvegarde locale est valide
    fi
fi

# ── Rotation : suppression des anciennes sauvegardes ──────────────────────────
log "Suppression des sauvegardes de plus de ${BACKUP_RETENTION} jours..."
DELETED=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime "+${BACKUP_RETENTION}" -print -delete | wc -l)
log "$DELETED ancien(s) fichier(s) supprimé(s)."

# ── Résumé ────────────────────────────────────────────────────────────────────
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
log "=== Sauvegarde terminée. Fichiers conservés : $TOTAL_BACKUPS ($TOTAL_SIZE) ==="
```

Rendez-le exécutable :
```bash
chmod +x scripts/backup_db.sh
```

Créez le fichier de configuration `.env.backup` (ne jamais committer ce fichier).
Sur une flotte GitSky, chaque projet a **son propre conteneur** `{projet}_db` et
sa base au nom du projet (Chap 18 §2) : ces valeurs viennent donc de
`.env.backup`, pré-rempli à la génération, jamais codées en dur. Le générateur
produit d'ailleurs un `.env.backup.example` déjà renseigné pour le projet.

```bash
# .env.backup — configuration du script de sauvegarde (projet « pain-scraper »)
POSTGRES_CONTAINER=pain-scraper_db
POSTGRES_DB=pain_scraper
POSTGRES_USER=pain_scraper
BACKUP_DIR=/backups/postgres
BACKUP_RETENTION=14
# S3_BUCKET=mon-bucket-backups        # décommenter si S3 disponible
# ALERT_EMAIL=admin@mondomaine.com    # décommenter pour les alertes email
```

### Automatisation avec Cron

Sur votre serveur Linux, éditez la crontab :
```bash
crontab -e
```

Ajoutez ces lignes :
```cron
# Sauvegarde quotidienne à 2h00 du matin
0 2 * * * /opt/gitsky/scripts/backup_db.sh >> /var/log/gitsky_backup.log 2>&1

# Vérification hebdomadaire que les sauvegardes existent bien
0 9 * * 1 /opt/gitsky/scripts/check_backups.sh >> /var/log/gitsky_backup.log 2>&1
```

### Alternative : Service Docker dédié aux Sauvegardes

Si vous préférez tout gérer dans Docker Compose, ajoutez ce service dans `docker-compose.prod.yml` :

```yaml
# À ajouter dans docker-compose.prod.yml

  backup:
    image: postgres:16-alpine
    restart: "no"  # Ne démarre pas automatiquement, lancé par cron
    environment:
      PGPASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - /backups/postgres:/backups
    networks:
      - internal
    command: >
      sh -c "pg_dump -h postgres -U ${POSTGRES_USER} ${POSTGRES_DB}
             | gzip > /backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz
             && find /backups -name '*.sql.gz' -mtime +14 -delete
             && echo 'Backup done.'"
    depends_on:
      - postgres
    profiles:
      - backup  # Lancé uniquement avec --profile backup
```

Cron pour lancer ce service :
```cron
0 2 * * * cd /opt/gitsky && docker compose -f docker-compose.prod.yml --profile backup run --rm backup
```

### Tester la Restauration — Obligatoire

**Une sauvegarde non testée n'est pas une sauvegarde.** Chaque mois, vérifiez que vous pouvez restaurer :

```bash
#!/usr/bin/env bash
# scripts/test_restore.sh
# Restaure la dernière sauvegarde dans un conteneur de test et vérifie le contenu.

BACKUP_DIR="/backups/postgres"
LATEST=$(ls -t "$BACKUP_DIR"/backup_*.sql.gz | head -1)

if [[ -z "$LATEST" ]]; then
    echo "ERREUR : Aucune sauvegarde trouvée dans $BACKUP_DIR"
    exit 1
fi

echo "Test de restauration depuis : $LATEST"

# Démarrer un PostgreSQL de test
docker run -d --name pg_restore_test \
    -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB=gitsky_test \
    postgres:16-alpine

sleep 3

# Restaurer
gunzip -c "$LATEST" | docker exec -i pg_restore_test \
    psql -U postgres gitsky_test

# Vérifier que les tables principales existent
RESULT=$(docker exec pg_restore_test \
    psql -U postgres gitsky_test -t -c "
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'public';
    ")

# Nettoyage
docker rm -f pg_restore_test

echo "Tables restaurées : $RESULT"
if [[ "$RESULT" -gt 0 ]]; then
    echo "✓ Test de restauration réussi."
else
    echo "✗ ERREUR : Aucune table trouvée après restauration !"
    exit 1
fi
```

---

## Partie 2 : Durcissement de la Sécurité

### 2.1 Principe du Moindre Privilège pour PostgreSQL

Par défaut, votre application se connecte probablement en tant que superutilisateur `postgres`. C'est l'équivalent de faire tourner votre serveur web en tant que `root` : si quelqu'un exploite une faille dans votre API, il obtient un accès total à votre base de données.

La solution est de créer un utilisateur applicatif avec uniquement les droits nécessaires :

```sql
-- Connectez-vous à PostgreSQL en tant que superutilisateur
-- docker exec -it gitsky_db psql -U postgres

-- 1. Créer l'utilisateur applicatif
CREATE USER gitsky_app WITH PASSWORD 'mot_de_passe_fort_ici';

-- 2. Donner accès à la base uniquement
GRANT CONNECT ON DATABASE gitsky TO gitsky_app;
GRANT USAGE ON SCHEMA public TO gitsky_app;

-- 3. Donner les permissions CRUD (pas DROP, pas CREATE TABLE)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gitsky_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gitsky_app;

-- 4. Appliquer ces droits aux futures tables (créées par les migrations)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gitsky_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO gitsky_app;

-- 5. L'utilisateur de migration (Alembic) doit garder des droits de DDL
--    Créer un utilisateur séparé pour les migrations
CREATE USER gitsky_migrate WITH PASSWORD 'autre_mot_de_passe_fort';
GRANT ALL PRIVILEGES ON DATABASE gitsky TO gitsky_migrate;
```

Mettez ensuite à jour votre `.env` :
```env
# Connexion applicative (lecture/écriture uniquement) — driver async
DATABASE_URL=postgresql+asyncpg://gitsky_app:mot_de_passe_fort@postgres/gitsky

# Connexion migrations (droits DDL complets) — driver async (env.py Alembic async)
DATABASE_URL_MIGRATE=postgresql+asyncpg://gitsky_migrate:autre_mdp@postgres/gitsky
```

### 2.2 Calendrier de Rotation des Secrets

La rotation régulière des secrets limite la fenêtre d'exposition en cas de fuite silencieuse (credential stuffing, ancien développeur, log accidentel).

```text
┌─────────────────────────────────────┬────────────┬────────────────────────┐
│ SECRET                              │ FRÉQUENCE  │ COMMENT FAIRE          │
├─────────────────────────────────────┼────────────┼────────────────────────┤
│ SECRET_KEY (JWT)                    │ 6 mois     │ Tous les tokens        │
│                                     │            │ existants sont         │
│                                     │            │ invalidés → re-login   │
├─────────────────────────────────────┼────────────┼────────────────────────┤
│ POSTGRES_PASSWORD                   │ 6 mois     │ Changer dans Postgres  │
│                                     │            │ + .env + redéployer    │
├─────────────────────────────────────┼────────────┼────────────────────────┤
│ SMTP_PASSWORD                       │ 1 an       │ Via interface du       │
│                                     │            │ fournisseur email      │
├─────────────────────────────────────┼────────────┼────────────────────────┤
│ STRIPE_SECRET_KEY                   │ Si compromis│ Via Stripe Dashboard  │
│ STRIPE_WEBHOOK_SECRET               │ uniquement │ Révoquer l'ancien      │
├─────────────────────────────────────┼────────────┼────────────────────────┤
│ Clés SSH serveur                    │ 1 an       │ Générer nouvelle paire │
│                                     │            │ + supprimer l'ancienne │
└─────────────────────────────────────┴────────────┴────────────────────────┘
```

Générer une nouvelle `SECRET_KEY` :
```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

Procédure de rotation sans interruption pour `SECRET_KEY` :
```python
# Dans config.py, vous pouvez temporairement accepter deux clés
# pendant une période de transition (ex: 24h) :

SECRET_KEY = "nouvelle_clé_principale"
SECRET_KEY_OLD = "ancienne_clé"  # Retirer après 24h

# Dans le middleware JWT :
# Essayer de vérifier avec la nouvelle clé,
# si ça échoue, essayer avec l'ancienne.
# Ainsi les utilisateurs connectés ne sont pas déconnectés brutalement.
```

### 2.3 Vérification du Réseau : PostgreSQL ne doit Jamais être Exposé

PostgreSQL doit être strictement interne. Vérifiez avec ce script :

```bash
#!/usr/bin/env bash
# scripts/check_security.sh
# Audit rapide de la surface d'exposition réseau.

set -euo pipefail

echo "=== Audit de sécurité réseau ==="
ERRORS=0

# 1. PostgreSQL ne doit pas écouter sur 0.0.0.0
PG_BINDING=$(docker inspect gitsky_db \
    --format='{{range $p, $b := .NetworkSettings.Ports}}{{$p}} -> {{$b}}{{end}}' 2>/dev/null || echo "")

if echo "$PG_BINDING" | grep -q "0.0.0.0"; then
    echo "✗ CRITIQUE : PostgreSQL est exposé publiquement ! ($PG_BINDING)"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ PostgreSQL non exposé publiquement."
fi

# 2. Port 5432 ne doit pas être accessible depuis l'extérieur
if timeout 3 bash -c "echo > /dev/tcp/localhost/5432" 2>/dev/null; then
    echo "✗ AVERTISSEMENT : Port 5432 accessible en local. Vérifiez les règles firewall."
else
    echo "✓ Port 5432 non accessible depuis l'hôte."
fi

# 3. Vérifier que les fichiers .env ne sont pas dans git
if git -C "$(dirname "$0")/.." ls-files --error-unmatch .env 2>/dev/null; then
    echo "✗ CRITIQUE : Le fichier .env est tracké par git !"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ .env non tracké par git."
fi

# 4. Vérifier les permissions des fichiers de secrets
for file in .env .env.backup .env.prod; do
    if [[ -f "$file" ]]; then
        PERMS=$(stat -c "%a" "$file")
        if [[ "$PERMS" != "600" ]] && [[ "$PERMS" != "400" ]]; then
            echo "✗ AVERTISSEMENT : $file a des permissions trop larges ($PERMS). Recommandé: 600"
            echo "  Corriger avec : chmod 600 $file"
        else
            echo "✓ Permissions de $file : OK ($PERMS)"
        fi
    fi
done

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "=== $ERRORS problème(s) critique(s) détecté(s). Action immédiate requise. ==="
    exit 1
else
    echo "=== Audit terminé. Aucun problème critique. ==="
fi
```

### 2.4 Scan des Vulnérabilités dans les Dépendances

Les bibliothèques tierces introduisent régulièrement des CVE (failles connues). Scannez-les mensuellement :

```bash
# Backend Python
pip install pip-audit
pip-audit -r backend/requirements.txt

# Frontend Node.js
cd frontend && npm audit

# Pour un rapport détaillé avec les corrections suggérées
npm audit fix --dry-run
```

Ajoutez ce contrôle dans votre CI/CD (GitHub Actions) :

```yaml
# .github/workflows/security.yml
name: Security Audit

on:
  schedule:
    - cron: '0 8 * * 1'  # Chaque lundi matin
  push:
    paths:
      - 'backend/requirements.txt'
      - 'frontend/package.json'

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Python dependency audit
        run: |
          pip install pip-audit
          pip-audit -r backend/requirements.txt

      - name: Node.js dependency audit
        working-directory: frontend
        run: npm audit --audit-level=high
```

---

## Partie 3 : Santé de la Base de Données PostgreSQL

### 3.1 Comprendre l'Autovacuum

PostgreSQL ne supprime pas physiquement les lignes quand vous faites un `DELETE` ou `UPDATE`. Il les marque comme "mortes" (dead tuples) et laisse un processus d'arrière-plan, **autovacuum**, les nettoyer périodiquement. Si l'autovacuum ne suit pas la cadence d'écriture, la table gonfle et les performances se dégradent.

Ce script de diagnostic vous donne une vue claire de l'état de vos tables :

```sql
-- scripts/db_health.sql
-- Exécuter avec : docker exec -i gitsky_db psql -U postgres gitsky < scripts/db_health.sql

\echo '=== État des tables (lignes mortes vs vivantes) ==='
SELECT
    schemaname,
    relname                                                     AS table_name,
    n_live_tup                                                  AS lignes_vivantes,
    n_dead_tup                                                  AS lignes_mortes,
    CASE WHEN n_live_tup > 0
         THEN round(100.0 * n_dead_tup / n_live_tup, 1)
         ELSE 0
    END                                                         AS pct_mortes,
    last_autovacuum::date                                       AS dernier_vacuum,
    last_autoanalyze::date                                      AS dernier_analyze,
    pg_size_pretty(pg_total_relation_size(relid))               AS taille_totale
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 15;

\echo ''
\echo '=== Taille de la base ==='
SELECT pg_size_pretty(pg_database_size(current_database())) AS taille_base;

\echo ''
\echo '=== 10 plus grosses tables ==='
SELECT
    relname                                                     AS table_name,
    pg_size_pretty(pg_total_relation_size(relid))               AS taille_totale,
    pg_size_pretty(pg_relation_size(relid))                     AS taille_donnees,
    pg_size_pretty(pg_total_relation_size(relid)
                   - pg_relation_size(relid))                   AS taille_index
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

\echo ''
\echo '=== Requêtes les plus lentes (si pg_stat_statements activé) ==='
SELECT
    round(total_exec_time::numeric, 2)                          AS temps_total_ms,
    calls,
    round((total_exec_time / calls)::numeric, 2)                AS temps_moyen_ms,
    left(query, 100)                                            AS requête
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

Exécution :
```bash
docker exec -i gitsky_db psql -U postgres gitsky < scripts/db_health.sql
```

**Interprétation :**
- `pct_mortes > 20%` avec `dernier_vacuum` vieux de plusieurs jours → VACUUM manuel recommandé
- Une table dont la `taille_index` dépasse la `taille_données` → indices potentiellement redondants

VACUUM manuel si nécessaire :
```bash
docker exec gitsky_db psql -U postgres gitsky -c "VACUUM ANALYZE;"
```

### 3.2 Vérification de la Taille du Disque

Le disque plein est la cause numéro un de corruption silencieuse en production. PostgreSQL ne peut plus écrire dans son WAL, les transactions échouent, et la base peut nécessiter une réparation manuelle.

```bash
#!/usr/bin/env bash
# scripts/check_disk.sh
# Vérifie l'espace disque et alerte si le seuil est dépassé.

THRESHOLD_WARN=70   # Alerte à 70%
THRESHOLD_CRIT=85   # Critique à 85%
ALERT_EMAIL="${ALERT_EMAIL:-}"

check_path() {
    local path="$1"
    local label="$2"
    local usage

    usage=$(df "$path" 2>/dev/null | awk 'NR==2 {sub(/%/,"",$5); print $5}')
    if [[ -z "$usage" ]]; then return; fi

    if [[ "$usage" -ge "$THRESHOLD_CRIT" ]]; then
        echo "✗ CRITIQUE : $label à ${usage}% (seuil: ${THRESHOLD_CRIT}%)"
        [[ -n "$ALERT_EMAIL" ]] && \
            echo "Disque $label à ${usage}% sur $(hostname)" | \
            mail -s "[GitSky] ALERTE CRITIQUE: Disque presque plein" "$ALERT_EMAIL"
        return 1
    elif [[ "$usage" -ge "$THRESHOLD_WARN" ]]; then
        echo "⚠ ATTENTION : $label à ${usage}% (seuil d'alerte: ${THRESHOLD_WARN}%)"
        [[ -n "$ALERT_EMAIL" ]] && \
            echo "Disque $label à ${usage}% sur $(hostname)" | \
            mail -s "[GitSky] ATTENTION: Disque $label à ${usage}%" "$ALERT_EMAIL"
    else
        echo "✓ $label : ${usage}% utilisé"
    fi
}

echo "=== Vérification de l'espace disque - $(date) ==="
check_path "/"         "Disque principal"
check_path "/backups"  "Disque sauvegardes" 2>/dev/null || true

# Taille des logs Docker (peut devenir très volumineux)
DOCKER_LOG_SIZE=$(find /var/lib/docker/containers -name "*.log" \
    -exec du -ch {} + 2>/dev/null | tail -1 | cut -f1)
echo "   Logs Docker : $DOCKER_LOG_SIZE"
```

### 3.3 Rotation des Logs Docker

Par défaut, Docker accumule les logs de vos conteneurs indéfiniment. Sur un serveur avec peu de RAM et de disque, cela peut consommer des Go en quelques mois.

Configurez une limite globale dans `/etc/docker/daemon.json` :

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
```

Appliquez la configuration :
```bash
sudo systemctl restart docker
```

Ou par service dans `docker-compose.prod.yml` pour un contrôle plus fin :
```yaml
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  postgres:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"
```

---

## Partie 4 : Monitoring et Surveillance

### 4.1 Monitoring de Disponibilité

Vous devez être informé avant vos utilisateurs en cas de panne. Configurez un monitoring externe dès le premier jour.

**UptimeRobot (gratuit)** — recommandé pour démarrer :
1. Créez un compte sur [uptimerobot.com](https://uptimerobot.com)
2. Ajoutez un monitor HTTP(S) vers `https://api.votre-domaine.com/health`
3. Configurez les alertes email / Telegram / Slack
4. Fréquence de vérification : toutes les 5 minutes (plan gratuit)

L'endpoint `/health` est déjà présent dans le template GitSky (dans
`app/core/main.py`, monté à la racine — sans préfixe `/api/` — et servi sur le
sous-domaine `api.` du projet derrière Traefik, comme tout le reste du
backend). Le stack étant
**asynchrone** (SQLAlchemy async), la vérification base l'est aussi — et
l'endpoint conserve sa charge utile existante (modules activés) en plus du
statut base :

```python
# app/core/main.py
@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok", "database": "ok", "modules": settings.enabled_modules, ...}
```

Sans ce `SELECT 1`, `/health` répondrait `200` avec une base morte — l'incident
passerait inaperçu. Le `503` marque le conteneur non sain côté Traefik et fleet
dashboard.

**Alertes Traefik** — vérifiez vos logs d'accès pour détecter des anomalies :

```bash
#!/usr/bin/env bash
# scripts/check_errors.sh
# Analyse les logs Traefik pour détecter des taux d'erreurs anormaux.

CONTAINER="${TRAEFIK_CONTAINER:-traefik}"
WINDOW_MINUTES=60
THRESHOLD_5XX=10  # Alerte si plus de 10 erreurs 5xx en 1 heure

ERROR_COUNT=$(docker logs "$CONTAINER" --since "${WINDOW_MINUTES}m" 2>&1 \
    | grep -c '"status":5' || true)

if [[ "$ERROR_COUNT" -ge "$THRESHOLD_5XX" ]]; then
    echo "✗ ALERTE : $ERROR_COUNT erreurs 5xx détectées dans la dernière heure."
    [[ -n "${ALERT_EMAIL:-}" ]] && \
        echo "$ERROR_COUNT erreurs 5xx en ${WINDOW_MINUTES} minutes sur $(hostname)" | \
        mail -s "[GitSky] Taux d'erreurs anormal" "$ALERT_EMAIL"
else
    echo "✓ Taux d'erreurs normal : $ERROR_COUNT erreur(s) 5xx (seuil: $THRESHOLD_5XX)"
fi
```

### 4.2 Monitoring Applicatif avec les SecurityEvents

Votre template intègre déjà un `SecurityMiddleware` qui enregistre les comportements suspects dans la table `security_events`. Consultez-la régulièrement :

```sql
-- Événements de sécurité des dernières 24h
SELECT
    event_type,
    severity,
    ip_address,
    COUNT(*)       AS occurrences,
    MAX(created_at) AS dernier_vu
FROM security_events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY event_type, severity, ip_address
ORDER BY occurrences DESC
LIMIT 20;

-- IPs suspectes (> 100 événements en 1h)
SELECT ip_address, COUNT(*) AS nb_events
FROM security_events
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY ip_address
HAVING COUNT(*) > 100
ORDER BY nb_events DESC;
```

Si vous détectez une IP récurrente dans les événements critiques, bloquez-la au niveau Traefik ou avec `ufw` :
```bash
# Bloquer une IP avec le firewall Linux
sudo ufw deny from 1.2.3.4 to any
```

---

## Partie 5 : Mises à Jour

### Stratégie de Mise à Jour

Ne jamais mettre à jour en production sans d'abord tester sur un environnement de staging. Le principe est : **staging d'abord, production ensuite**.

```text
Développement → Staging (clone de prod) → Production
```

### Images Docker

```bash
#!/usr/bin/env bash
# scripts/update_images.sh
# Met à jour les images Docker et redémarre les services.

set -euo pipefail

PROJECT_DIR="/opt/gitsky"
COMPOSE_FILE="docker-compose.prod.yml"

cd "$PROJECT_DIR"

echo "=== Mise à jour des images Docker - $(date) ==="

# Récupérer les nouvelles versions des images de base. Épingler une LTS
# SUPPORTÉE : Node 20 est en fin de vie depuis 2026-04-30 — utiliser Node 24
# (LTS active), sans quoi la base ne reçoit plus de correctifs de sécurité.
docker pull postgres:16.3-alpine
docker pull node:24-alpine
docker pull python:3.12-slim
docker pull traefik:v3.1

# Reconstruire les images applicatives (Compose v2 : `docker compose`, pas
# `docker-compose` v1 déprécié).
docker compose -f "$COMPOSE_FILE" build --no-cache

# Redémarrer avec les nouvelles images (zéro downtime si répliqué)
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Supprimer les anciennes images non utilisées
docker image prune -f

echo "=== Mise à jour terminée ==="
```

### Système d'Exploitation

```bash
#!/usr/bin/env bash
# scripts/update_os.sh
# Met à jour le système et redémarre si nécessaire (Debian/Ubuntu).

set -euo pipefail

echo "=== Mise à jour du système - $(date) ==="

apt-get update -qq
apt-get upgrade -y --no-install-recommends
apt-get autoremove -y
apt-get autoclean

# Vérifier si un redémarrage est nécessaire
if [[ -f /var/run/reboot-required ]]; then
    echo "⚠ Un redémarrage est requis pour appliquer les mises à jour kernel."
    echo "  Planifiez un redémarrage en maintenance : sudo reboot"
else
    echo "✓ Aucun redémarrage requis."
fi

echo "=== Mise à jour OS terminée ==="
```

### Dépendances Applicatives

```bash
#!/usr/bin/env bash
# scripts/audit_dependencies.sh
# Scan de sécurité des dépendances Python et Node.js.

set -uo pipefail
ERRORS=0

echo "=== Audit des dépendances - $(date) ==="

# Python
echo "--- Backend Python ---"
if pip-audit -r /opt/gitsky/backend/requirements.txt 2>&1; then
    echo "✓ Aucune CVE Python détectée."
else
    echo "✗ Des vulnérabilités ont été détectées dans les dépendances Python."
    ERRORS=$((ERRORS + 1))
fi

# Node.js
echo "--- Frontend Node.js ---"
if (cd /opt/gitsky/frontend && npm audit --audit-level=high 2>&1); then
    echo "✓ Aucune CVE Node.js critique détectée."
else
    echo "✗ Des vulnérabilités critiques ont été détectées dans les dépendances Node.js."
    ERRORS=$((ERRORS + 1))
fi

exit $ERRORS
```

---

## Partie 6 : Calendrier de Maintenance

### Tableau de Bord Récapitulatif

```text
┌──────────────┬────────────────────────────────────────────────────┬──────────┐
│ FRÉQUENCE    │ TÂCHE                                              │ DURÉE    │
├──────────────┼────────────────────────────────────────────────────┼──────────┤
│ QUOTIDIEN    │ ✦ Sauvegarde PostgreSQL (automatique via cron)     │ 0 min    │
│ (automatique)│ ✦ Vérification de l'espace disque (cron)          │ 0 min    │
│              │ ✦ Monitoring de disponibilité (UptimeRobot)        │ 0 min    │
├──────────────┼────────────────────────────────────────────────────┼──────────┤
│ HEBDOMADAIRE │ ✦ Révision des logs d'erreurs (Traefik + app)      │ 10 min   │
│ (manuel)     │ ✦ Révision des SecurityEvents suspects             │ 5 min    │
│              │ ✦ Vérifier que la dernière sauvegarde existe       │ 2 min    │
│              │ ✦ Vérifier les alertes UptimeRobot                 │ 2 min    │
├──────────────┼────────────────────────────────────────────────────┼──────────┤
│ MENSUEL      │ ✦ Mise à jour OS + images Docker                   │ 30 min   │
│ (manuel)     │ ✦ Scan CVE des dépendances (pip-audit, npm audit)  │ 15 min   │
│              │ ✦ Test de restauration d'une sauvegarde            │ 20 min   │
│              │ ✦ Analyse de la santé DB (db_health.sql)           │ 10 min   │
│              │ ✦ Révision des logs Docker (taille)                │ 5 min    │
├──────────────┼────────────────────────────────────────────────────┼──────────┤
│ SEMESTRIEL   │ ✦ Rotation SECRET_KEY (re-login de tous les users) │ 15 min   │
│ (manuel)     │ ✦ Rotation du mot de passe PostgreSQL              │ 15 min   │
│              │ ✦ Révision des utilisateurs DB (supprimer inactifs)│ 10 min   │
│              │ ✦ Révision des clés SSH autorisées sur le serveur  │ 10 min   │
│              │ ✦ Mise à jour de la politique de sauvegarde        │ 15 min   │
├──────────────┼────────────────────────────────────────────────────┼──────────┤
│ SUR INCIDENT │ ✦ Rotation immédiate de TOUS les secrets           │          │
│              │ ✦ Analyse des logs autour de l'heure de l'incident │          │
│              │ ✦ Vérification de l'intégrité des données          │          │
│              │ ✦ Notification des utilisateurs si données exposées│          │
└──────────────┴────────────────────────────────────────────────────┴──────────┘
```

### Crontab Complète Recommandée

Voici la crontab complète à installer sur votre serveur de production :

```cron
# ============================================================
# Crontab GitSky — Maintenance Automatisée
# Installer avec : crontab -e
# ============================================================

# Variables d'environnement
MAILTO=""
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# ── Sauvegardes ─────────────────────────────────────────────
# Sauvegarde quotidienne à 2h00
0 2 * * * /opt/gitsky/scripts/backup_db.sh >> /var/log/gitsky_backup.log 2>&1

# ── Surveillance disque ──────────────────────────────────────
# Vérification de l'espace disque toutes les heures
0 * * * * /opt/gitsky/scripts/check_disk.sh >> /var/log/gitsky_monitor.log 2>&1

# ── Surveillance des erreurs ─────────────────────────────────
# Analyse des logs d'erreurs toutes les heures
30 * * * * /opt/gitsky/scripts/check_errors.sh >> /var/log/gitsky_monitor.log 2>&1

# ── Audit de sécurité ────────────────────────────────────────
# Audit de sécurité réseau chaque dimanche à 3h
0 3 * * 0 /opt/gitsky/scripts/check_security.sh >> /var/log/gitsky_security.log 2>&1

# Scan CVE des dépendances le 1er de chaque mois
0 4 1 * * /opt/gitsky/scripts/audit_dependencies.sh >> /var/log/gitsky_security.log 2>&1

# ── Mises à jour ─────────────────────────────────────────────
# Mise à jour de sécurité OS chaque lundi à 4h (sans redémarrage auto)
0 4 * * 1 apt-get update -qq && apt-get upgrade -y -o Dpkg::Options::="--force-confdef" >> /var/log/gitsky_updates.log 2>&1

# ── Nettoyage ────────────────────────────────────────────────
# Nettoyage des images Docker non utilisées chaque dimanche
0 5 * * 0 docker image prune -f >> /var/log/gitsky_cleanup.log 2>&1

# Rotation des logs de maintenance (garder 30 jours)
0 6 1 * * find /var/log/gitsky_*.log -mtime +30 -delete 2>/dev/null || true
```

---

## Partie 7 : Procédures d'Urgence

### Restauration d'Urgence

En cas de corruption ou de suppression accidentelle :

```bash
#!/usr/bin/env bash
# scripts/emergency_restore.sh
# Restaure la base depuis la dernière sauvegarde.
#
# ATTENTION : Ceci remplace TOUTES les données actuelles.
# Faire une sauvegarde de l'état actuel avant de lancer si possible.
#
# Usage : ./scripts/emergency_restore.sh [chemin/vers/backup.sql.gz]

set -euo pipefail

BACKUP_DIR="/backups/postgres"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-gitsky_db}"
POSTGRES_DB="${POSTGRES_DB:-gitsky}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

# Choisir la sauvegarde
if [[ -n "${1:-}" ]]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/backup_*.sql.gz | head -1)
    echo "Utilisation de la dernière sauvegarde : $BACKUP_FILE"
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERREUR : Fichier de sauvegarde introuvable : $BACKUP_FILE"
    exit 1
fi

echo "=== RESTAURATION D'URGENCE ==="
echo "Source  : $BACKUP_FILE"
echo "Cible   : base '$POSTGRES_DB' dans le conteneur '$POSTGRES_CONTAINER'"
echo ""
echo "ATTENTION : Cette opération va écraser toutes les données actuelles."
read -p "Confirmez-vous ? (tapez 'OUI' en majuscules) : " CONFIRM

if [[ "$CONFIRM" != "OUI" ]]; then
    echo "Restauration annulée."
    exit 0
fi

# Arrêter l'application pour éviter les écritures pendant la restauration
echo "1/4 Arrêt des services applicatifs..."
cd /opt/gitsky && docker compose -f docker-compose.prod.yml stop backend

# Réinitialiser la base
echo "2/4 Réinitialisation de la base..."
docker exec "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -c "
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();
    "
docker exec "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS ${POSTGRES_DB}_old;"
docker exec "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -c "ALTER DATABASE $POSTGRES_DB RENAME TO ${POSTGRES_DB}_old;"
docker exec "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"

# Restaurer
echo "3/4 Restauration des données..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" "$POSTGRES_DB"

# Redémarrer
echo "4/4 Redémarrage des services..."
docker compose -f docker-compose.prod.yml up -d backend

echo ""
echo "=== Restauration terminée ==="
echo "L'ancienne base est préservée sous le nom '${POSTGRES_DB}_old'."
echo "Supprimez-la après vérification : DROP DATABASE ${POSTGRES_DB}_old;"
```

### Checklist Post-Incident

Après tout incident de sécurité (accès non autorisé, fuite de données suspectée) :

```text
□ Isoler le système si nécessaire (couper le trafic entrant dans Traefik)
□ Sauvegarder l'état actuel AVANT toute modification (pour l'analyse)
□ Identifier l'étendue : quelles données, quelle fenêtre temporelle ?
□ Révoquer TOUS les tokens JWT actifs (changer SECRET_KEY)
□ Rotater TOUS les secrets (DB, Stripe, SMTP)
□ Analyser les logs Traefik et SecurityEvents autour de l'heure de l'incident
□ Corriger la vulnérabilité exploitée
□ Restaurer depuis sauvegarde si données corrompues
□ Notifier les utilisateurs affectés (RGPD : obligation sous 72h si données personnelles)
□ Documenter l'incident (timeline, impact, mesures prises)
□ Mettre en place des contrôles pour éviter la récurrence
```

---

## Maintenance à l'Échelle de la Flotte

Les procédures précédentes valent projet par projet. Sur une flotte de 20-30
projets, elles doivent être **orchestrées** depuis le fleet dashboard
(Chap 19) — sinon l'opérateur passe ses journées à jongler entre `ssh` et
`docker compose`.

### Sauvegarde Multi-Projets

Un cron unique boucle sur **tous les conteneurs de bases projet** et applique la
stratégie 3-2-1 à chacun. Chaque projet ayant son propre conteneur PostgreSQL
(Chap 18 §2), on énumère les conteneurs `*_db` — et non les bases d'une instance
partagée :

```bash
# scripts/backup-fleet.sh — extrait
#!/usr/bin/env bash
set -euo pipefail

DATE=$(date +%Y%m%d_%H%M%S)
S3_BUCKET="s3://mystudio-backups"

# Conteneurs de bases projet : convention de nommage {projet}_db.
CONTAINERS=$(docker ps --format '{{.Names}}' --filter 'name=_db$')

for container in $CONTAINERS; do
    project="${container%_db}"
    dbname="${project//-/_}"        # identifiant PostgreSQL (pas de tiret)
    echo "Sauvegarde de $project..."
    docker exec "$container" pg_dump -U postgres -Fc "$dbname" \
        | gzip > "/backups/${dbname}_${DATE}.dump.gz"
    aws s3 cp "/backups/${dbname}_${DATE}.dump.gz" "$S3_BUCKET/$project/"
done

# Rotation : garder 14 jours de dumps locaux
find /backups -name "*.dump.gz" -mtime +14 -delete
```

Ce script tourne à 02:00 UTC, en heure creuse — avant que le trafic de la
journée ne reprenne sur la flotte.

### Vérification des Sauvegardes de Flotte

Le fleet dashboard expose une colonne « dernière sauvegarde OK » par projet.
Un cron hebdomadaire teste la restauration d'un projet aléatoire dans un
environnement de staging pour vérifier que les dumps sont exploitables.

Une sauvegarde jamais restaurée est une sauvegarde inutile.

### Rotation des Secrets

À l'échelle d'une flotte, la rotation manuelle des secrets projet par
projet est irréaliste. Le fleet dashboard automatise :

- **Rotation trimestrielle des secrets DB** : le fleet dashboard génère
  un nouveau mot de passe, l'applique dans PostgreSQL, met à jour le
  `.env` du projet, et redémarre le conteneur.
- **Rotation semestrielle des `SECRET_KEY`** : idem, avec invalidation
  automatique de toutes les sessions actives.

Les secrets Stripe et LLM proxy sont mutualisés au niveau flotte et donc
rotatés une seule fois pour tous les projets.

### Monitoring de Disponibilité de Flotte

Un unique cron toutes les 60 secondes interroge `/health` sur tous les
projets. Un projet muet depuis plus de 5 minutes déclenche l'alerte
`deployment_failed` du fleet dashboard (Chap 19). L'opérateur voit
l'incident sur son dashboard matinal et peut consulter les logs live
sans SSH.

### Alerte Disque Consolidée

Sur un VPS mutualisé, le remplissage disque peut venir d'un unique projet
qui log excessivement. Une jauge par projet dans le fleet dashboard,
alimentée par `docker system df -v`, identifie immédiatement le
responsable — bien plus rapide que de fouiller `du -sh /var/lib/docker/*`.

---

## Conclusion

La maintenance n'est pas une activité optionnelle : c'est ce qui distingue un projet de démonstration d'une plateforme en production fiable. Les trois piliers à mettre en place impérativement dès le premier jour sont :

1. **Les sauvegardes automatiques** — sans elles, tout le reste est inutile.
2. **Le monitoring de disponibilité** — savoir avant vos utilisateurs.
3. **L'alerte disque** — le disque plein est la panne la plus courante et la plus évitable.

Sur une flotte GitSky, ces trois piliers sont **mutualisés au niveau du fleet dashboard** — un seul cron de sauvegardes, un seul monitoring, une seule alerte disque consolidée. Cette centralisation transforme la maintenance d'une activité chronophage à N projets en une routine matinale de 10 minutes sur un tableau unique.

Une fois ces fondations posées, les autres pratiques de ce chapitre peuvent être intégrées progressivement, en commençant par celles qui correspondent aux risques les plus élevés (données financières Stripe → rotation des secrets en priorité).
