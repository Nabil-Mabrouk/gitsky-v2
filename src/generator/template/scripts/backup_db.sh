#!/usr/bin/env bash
# =============================================================================
# scripts/backup_db.sh — Sauvegarde PostgreSQL du projet, rotation + alerte.
# (Chap 23, Partie 1 — adapté GitSky : conteneur PAR PROJET, config .env.backup)
#
# Usage : ./scripts/backup_db.sh
# Config lue depuis .env.backup (à la racine du projet), sinon défauts :
#   POSTGRES_CONTAINER  — conteneur Docker PostgreSQL du projet ({nom}_db)
#   POSTGRES_DB         — base du projet
#   POSTGRES_USER       — utilisateur PostgreSQL
#   BACKUP_DIR          — répertoire local des dumps
#   BACKUP_RETENTION    — jours de rétention (défaut : 14)
#   S3_BUCKET           — bucket S3 hors-site (optionnel — règle 3-2-1)
#   ALERT_EMAIL         — email d'alerte en cas d'échec (optionnel)
#
# NB (écart Chap 23) : le livre code en dur `hitl_postgres_1` / la base `hitl`.
# Sur une flotte GitSky chaque projet a son propre conteneur `{nom}_db` : ces
# noms VIENNENT donc de .env.backup (pré-rempli à la génération), jamais du code.
# =============================================================================

set -euo pipefail

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

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

alert() {
    local message="$1"
    log "ERREUR: $message"
    if [[ -n "${ALERT_EMAIL:-}" ]]; then
        echo "$message" | mail -s "[GitSky] ALERTE: Échec sauvegarde ${POSTGRES_DB}" \
            "$ALERT_EMAIL" 2>/dev/null || true
    fi
}

# ÉCART AU LIVRE : le script du Chap 23 appelle `log` (qui écrit dans
# $BACKUP_DIR/backup.log via tee) AVANT le `mkdir -p "$BACKUP_DIR"`. Avec
# `set -o pipefail`, la toute première sauvegarde échoue tant que le dossier
# n'existe pas. On crée le dossier d'abord.
mkdir -p "$BACKUP_DIR"

log "=== Démarrage de la sauvegarde (${POSTGRES_DB}) ==="

# Le conteneur du projet doit tourner.
if ! docker inspect "$POSTGRES_CONTAINER" --format='{{.State.Status}}' 2>/dev/null \
        | grep -q "running"; then
    alert "Le conteneur $POSTGRES_CONTAINER n'est pas en cours d'exécution."
    exit 1
fi

log "Dump de '$POSTGRES_DB' vers $BACKUP_FILE..."
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

# Une sauvegarde corrompue est pire qu'une absence de sauvegarde : on vérifie.
log "Vérification de l'intégrité..."
if ! gzip -t "$BACKUP_FILE"; then
    alert "Fichier de sauvegarde corrompu : $BACKUP_FILE"
    rm -f "$BACKUP_FILE"
    exit 1
fi
log "Intégrité OK."

# Copie hors-site (règle 3-2-1) — l'échec S3 n'invalide pas la sauvegarde locale.
if [[ -n "${S3_BUCKET:-}" ]]; then
    log "Upload vers s3://${S3_BUCKET}/${POSTGRES_DB}/..."
    if aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/${POSTGRES_DB}/" \
            --storage-class STANDARD_IA; then
        log "Upload S3 réussi."
    else
        alert "Upload S3 échoué. La sauvegarde locale est conservée."
    fi
fi

log "Rotation : suppression des sauvegardes de plus de ${BACKUP_RETENTION} jours..."
DELETED=$(find "$BACKUP_DIR" -name "backup_${POSTGRES_DB}_*.sql.gz" \
    -mtime "+${BACKUP_RETENTION}" -print -delete | wc -l)
log "$DELETED ancien(s) fichier(s) supprimé(s)."

TOTAL=$(find "$BACKUP_DIR" -name "backup_${POSTGRES_DB}_*.sql.gz" | wc -l)
log "=== Sauvegarde terminée. Dumps conservés : $TOTAL ==="
