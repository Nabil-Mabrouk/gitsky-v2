#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/backup-fleet.sh — Sauvegarde 3-2-1 de TOUTE la flotte.
# (Chap 23 §« Sauvegarde Multi-Projets »)
#
# Tourne à 02:00 UTC, AVANT le kill_check de 03:00 : les projets sur le point
# d'être tués ont ainsi une sauvegarde fraîche.
#
# ÉCART AU LIVRE (décision d'archi Phase 6) : le Chap 23 énumère les bases via
# `SELECT datname FROM pg_database` d'une instance PostgreSQL PARTAGÉE. GitSky a
# retenu un conteneur PostgreSQL PAR PROJET (isolation CPU/IO, plafond de
# connexions). On boucle donc sur les CONTENEURS `*_db` de la flotte, un pg_dump
# chacun — chaque base est déjà isolée dans son conteneur.
# =============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
BACKUP_RETENTION="${BACKUP_RETENTION:-14}"
S3_BUCKET="${S3_BUCKET:-}"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Conteneurs de bases projet : convention de nommage `{projet}_db` (compose de prod).
CONTAINERS=$(docker ps --format '{{.Names}}' --filter 'name=_db$')

if [[ -z "$CONTAINERS" ]]; then
    echo "Aucun conteneur de base projet (*_db) en cours d'exécution."
    exit 0
fi

FAILED=0
for container in $CONTAINERS; do
    project="${container%_db}"          # pain-scraper_db -> pain-scraper
    dbname="${project//-/_}"            # identifiant PostgreSQL (pas de tiret)
    outfile="${BACKUP_DIR}/${dbname}_${DATE}.dump.gz"

    echo "Sauvegarde de $project (conteneur $container)..."
    # -U "$dbname" et non -U postgres : POSTGRES_USER == POSTGRES_DB == db_name
    # pour chaque projet (.env.jinja) — l'image officielle postgres ne crée le
    # rôle "postgres" QUE si POSTGRES_USER vaut "postgres" ; ici jamais le cas,
    # le rôle "postgres" n'existe simplement pas. Trouvé en testant contre un
    # vrai conteneur (le mock docker des tests ne valide aucun credential).
    if docker exec "$container" pg_dump -U "$dbname" -Fc "$dbname" | gzip > "$outfile"; then
        if [[ -n "$S3_BUCKET" ]]; then
            aws s3 cp "$outfile" "s3://${S3_BUCKET}/${project}/" || \
                echo "  ⚠ upload S3 échoué pour $project (dump local conservé)."
        fi
    else
        echo "  ✗ pg_dump a échoué pour $project."
        rm -f "$outfile"
        FAILED=$((FAILED + 1))
    fi
done

# Rotation : garder BACKUP_RETENTION jours de dumps locaux.
find "$BACKUP_DIR" -name "*.dump.gz" -mtime "+${BACKUP_RETENTION}" -delete

if [[ $FAILED -gt 0 ]]; then
    echo "=== Sauvegarde flotte terminée avec $FAILED échec(s). ==="
    exit 1
fi
echo "=== Sauvegarde flotte terminée. ==="
