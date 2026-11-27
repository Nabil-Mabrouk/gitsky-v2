#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/publish-docs.sh — Publie le guide d'exploitation
# (docs/exploitation/*.md du monorepo) dans l'onglet Apprentissage du fleet
# dashboard (https://0-hitl.com/learn), réservé aux comptes admin.
#
# Copie le dossier dans le conteneur backend du fleet dashboard (le monorepo
# n'y est pas monté : seul src/generator l'est), puis lance le seed générique
# du module tutorials (scripts/seed_tutorials.py, Chap 11). Rejouable : les
# pages sont mises à jour sur place, une page supprimée du dossier disparaît.
#
# Usage : publish-docs.sh            (après `git pull` dans /opt/gitsky/gitsky-v2)
# Variables : DOCS_DIR, FLEET_BACKEND_CONTAINER (défauts ci-dessous).
# =============================================================================

set -euo pipefail

DOCS_DIR="${DOCS_DIR:-/opt/gitsky/gitsky-v2/docs/exploitation}"
CONTAINER="${FLEET_BACKEND_CONTAINER:-fleet-dashboard_backend}"
TMP_IN_CONTAINER="/tmp/gitsky-exploitation"
SLUG="exploiter-gitsky"
TITLE="Exploiter GitSky"

if [[ $# -gt 0 ]]; then
    echo "Usage : $0   (aucun argument ; voir DOCS_DIR / FLEET_BACKEND_CONTAINER)" >&2
    exit 2
fi

if ! compgen -G "${DOCS_DIR}/*.md" > /dev/null; then
    echo "✗ aucun fichier .md dans ${DOCS_DIR} — git pull dans le monorepo ?" >&2
    exit 1
fi

docker exec -u 0 "$CONTAINER" rm -rf "$TMP_IN_CONTAINER"
docker cp "${DOCS_DIR}/." "${CONTAINER}:${TMP_IN_CONTAINER}"
docker exec "$CONTAINER" python -m scripts.seed_tutorials \
    --slug "$SLUG" --title "$TITLE" --lang fr --access-role admin \
    "$TMP_IN_CONTAINER"
docker exec -u 0 "$CONTAINER" rm -rf "$TMP_IN_CONTAINER"

echo "✓ Guide publié : https://0-hitl.com/learn (comptes admin)."
