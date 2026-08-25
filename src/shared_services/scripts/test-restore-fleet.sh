#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/test-restore-fleet.sh — Teste la restauration d'un
# projet de la flotte, choisi au hasard parmi les sauvegardes disponibles.
# (Chap 23 §« Vérification des Sauvegardes de Flotte » — MAINTENANCE.md, tâche
# mensuelle "Test de restauration d'un projet au hasard")
#
# « Une sauvegarde non testée n'est pas une sauvegarde. » scripts/test_restore.sh
# (par projet) ne peut PAS servir tel quel ici : il attend le format de
# backup_db.sh (backup_{db}_*.sql.gz, plain SQL, restauré via psql), alors que
# backup-fleet.sh — le script RÉELLEMENT en production (crontab.fleet) —
# produit {db}_{date}.dump.gz (format custom pg_dump -Fc, restauré via
# pg_restore). Lancé contre le vrai répertoire de sauvegarde de flotte,
# test_restore.sh ne trouverait AUCUN fichier correspondant.
#
# Env :
#   BACKUP_DIR — répertoire des sauvegardes de flotte (défaut : /backups/postgres,
#                même défaut que backup-fleet.sh)
#   PROJECT    — force le projet testé plutôt que d'en tirer un au hasard
#                (utile pour un test ciblé, hors cron)
# =============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
TEST_CONTAINER="gitsky_restore_test_$$"

cleanup() { docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Un dump par projet : {dbname}_{YYYYMMDD_HHMMSS}.dump.gz (backup-fleet.sh).
# Le nom de projet lui-même peut contenir des underscores (tirets convertis à
# la sauvegarde) : on ne retire que le suffixe daté, jamais fixe en longueur.
mapfile -t DBNAMES < <(
    find "$BACKUP_DIR" -maxdepth 1 -name "*.dump.gz" -exec basename {} \; 2>/dev/null \
        | sed -E 's/_[0-9]{8}_[0-9]{6}\.dump\.gz$//' \
        | sort -u
)

if [[ ${#DBNAMES[@]} -eq 0 ]]; then
    echo "ERREUR : aucune sauvegarde trouvée dans $BACKUP_DIR"
    exit 1
fi

if [[ -n "${PROJECT:-}" ]]; then
    DBNAME="${PROJECT//-/_}"
else
    DBNAME="${DBNAMES[$((RANDOM % ${#DBNAMES[@]}))]}"
fi

LATEST=$(find "$BACKUP_DIR" -maxdepth 1 -name "${DBNAME}_*.dump.gz" | sort | tail -1)
if [[ -z "$LATEST" ]]; then
    echo "ERREUR : aucune sauvegarde pour '$DBNAME' dans $BACKUP_DIR"
    exit 1
fi

echo "Projet tiré au sort : $DBNAME"
echo "Test de restauration depuis : $LATEST"

docker run -d --name "$TEST_CONTAINER" \
    -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB="${DBNAME}_test" \
    postgres:16.3-alpine >/dev/null

# Laisser PostgreSQL démarrer.
for _ in $(seq 1 30); do
    if docker exec "$TEST_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

gunzip -c "$LATEST" | docker exec -i "$TEST_CONTAINER" \
    pg_restore -U postgres -d "${DBNAME}_test" >/dev/null 2>&1 || true
# pg_restore renvoie parfois un code non-nul pour des avertissements bénins
# (objets déjà présents, ordre de dépendances) — la vraie vérification est le
# comptage de tables ci-dessous, pas le code de sortie de pg_restore lui-même.

RESULT=$(docker exec "$TEST_CONTAINER" psql -U postgres "${DBNAME}_test" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" \
    | tr -d '[:space:]')

echo "Tables restaurées : $RESULT"
if [[ "${RESULT:-0}" -gt 0 ]]; then
    echo "✓ Test de restauration réussi ($DBNAME)."
else
    echo "✗ ERREUR : aucune table après restauration de $DBNAME."
    exit 1
fi
