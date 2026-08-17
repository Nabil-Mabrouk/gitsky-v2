#!/usr/bin/env bash
# =============================================================================
# scripts/test_restore.sh — Restaure le dernier dump dans un conteneur jetable
# et vérifie qu'il contient des tables (Chap 23, Partie 1).
#
# « Une sauvegarde non testée n'est pas une sauvegarde. » À lancer mensuellement.
# Config .env.backup : BACKUP_DIR, POSTGRES_DB.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env.backup"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
POSTGRES_DB="${POSTGRES_DB:-gitsky}"
TEST_CONTAINER="gitsky_restore_test_$$"

LATEST=$(ls -t "$BACKUP_DIR"/backup_"${POSTGRES_DB}"_*.sql.gz 2>/dev/null | head -1 || true)
if [[ -z "$LATEST" ]]; then
    echo "ERREUR : aucune sauvegarde trouvée dans $BACKUP_DIR"
    exit 1
fi

echo "Test de restauration depuis : $LATEST"

cleanup() { docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$TEST_CONTAINER" \
    -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB="${POSTGRES_DB}_test" \
    postgres:16.3-alpine >/dev/null

# Laisser PostgreSQL démarrer.
for _ in $(seq 1 30); do
    if docker exec "$TEST_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

gunzip -c "$LATEST" | docker exec -i "$TEST_CONTAINER" \
    psql -U postgres "${POSTGRES_DB}_test" >/dev/null

RESULT=$(docker exec "$TEST_CONTAINER" psql -U postgres "${POSTGRES_DB}_test" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" \
    | tr -d '[:space:]')

echo "Tables restaurées : $RESULT"
if [[ "${RESULT:-0}" -gt 0 ]]; then
    echo "✓ Test de restauration réussi."
else
    echo "✗ ERREUR : aucune table après restauration."
    exit 1
fi
