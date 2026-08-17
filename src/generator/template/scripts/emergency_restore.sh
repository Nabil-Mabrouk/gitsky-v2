#!/usr/bin/env bash
# =============================================================================
# scripts/emergency_restore.sh — Restaure la base depuis la dernière sauvegarde.
# (Chap 23, Partie 7 — adapté GitSky : conteneur par projet, compose de prod)
#
# ATTENTION : écrase TOUTES les données actuelles. L'ancienne base est renommée
# {db}_old (et non supprimée) pour permettre une vérification après coup.
#
# Usage : ./scripts/emergency_restore.sh [chemin/vers/backup.sql.gz]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env.backup"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-gitsky_db}"
POSTGRES_DB="${POSTGRES_DB:-gitsky}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

if [[ -n "${1:-}" ]]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/backup_"${POSTGRES_DB}"_*.sql.gz 2>/dev/null | head -1 || true)
    echo "Dernière sauvegarde : $BACKUP_FILE"
fi

if [[ -z "${BACKUP_FILE:-}" || ! -f "$BACKUP_FILE" ]]; then
    echo "ERREUR : fichier de sauvegarde introuvable : ${BACKUP_FILE:-<aucun>}"
    exit 1
fi

echo "=== RESTAURATION D'URGENCE ==="
echo "Source : $BACKUP_FILE"
echo "Cible  : base '$POSTGRES_DB' (conteneur '$POSTGRES_CONTAINER')"
echo "ATTENTION : écrase toutes les données actuelles."
read -r -p "Confirmez ? (tapez 'OUI') : " CONFIRM
if [[ "$CONFIRM" != "OUI" ]]; then
    echo "Restauration annulée."
    exit 0
fi

echo "1/4 Arrêt du backend (stoppe les écritures)..."
( cd "$PROJECT_DIR" && docker compose stop backend )

echo "2/4 Bascule de l'ancienne base en ${POSTGRES_DB}_old..."
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
     WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c \
    "DROP DATABASE IF EXISTS ${POSTGRES_DB}_old;"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c \
    "ALTER DATABASE $POSTGRES_DB RENAME TO ${POSTGRES_DB}_old;"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c \
    "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;"

echo "3/4 Restauration des données..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$POSTGRES_CONTAINER" \
    psql -U "$POSTGRES_USER" "$POSTGRES_DB"

echo "4/4 Redémarrage du backend..."
( cd "$PROJECT_DIR" && docker compose up -d backend )

echo "=== Restauration terminée. Ancienne base préservée sous ${POSTGRES_DB}_old. ==="
echo "Après vérification : DROP DATABASE ${POSTGRES_DB}_old;"
