#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/backup-fleet.sh — Sauvegarde 3-2-1 de TOUTE la flotte.
# (Chap 23 §« Sauvegarde Multi-Projets »)
#
# Tourne à 02:00 UTC, AVANT le test de restauration mensuel de 04:00 : celui-ci
# a ainsi toujours une sauvegarde fraîche à vérifier.
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
# Archives des volumes de fichiers (voir plus bas) : bien plus lourdes qu'un
# dump, rétention propre pour ne pas saturer le disque du VPS.
VOLUME_RETENTION="${VOLUME_RETENTION:-7}"
VOLUME_DIR="${BACKUP_DIR}/volumes"
TAR_IMAGE="${TAR_IMAGE:-alpine:3.20}"
S3_BUCKET="${S3_BUCKET:-}"
# Copie HORS SERVEUR via rclone (2026-11-23) : /backups est sur le même disque
# que les données — sans copie externe, la perte du VPS emporte aussi toutes
# les sauvegardes. Remote rclone CHIFFRÉ (crypt) recommandé : les dumps
# contiennent emails et hachés de mots de passe des utilisateurs. Lu dans
# shared_services/.env (BACKUP_RCLONE_REMOTE, ex. "gitsky-crypt:fleet") si
# RCLONE_REMOTE n'est pas déjà fourni : le crontab installé n'a pas à changer.
SHARED_ENV="${SHARED_ENV:-/opt/gitsky/shared_services/.env}"
if [[ -z "${RCLONE_REMOTE:-}" && -f "$SHARED_ENV" ]]; then
    RCLONE_REMOTE="$(grep -E '^BACKUP_RCLONE_REMOTE=' "$SHARED_ENV" | tail -n1 | cut -d= -f2- || true)"
fi
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
OFFSITE_RETENTION="${OFFSITE_RETENTION:-30}"
# Durée max d'UN envoi (s). Bug réel (2026-11-23) : un `rclone copyto` figé
# 21 min sur un dump de 72 Mo (12 s relancé à la main) bloquait la sauvegarde
# de toute la flotte. Borné ici + délais réseau courts côté rclone.
OFFSITE_TIMEOUT="${OFFSITE_TIMEOUT:-1800}"
RCLONE_FLAGS=(--timeout 120s --contimeout 30s --retries 3 --low-level-retries 5)
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR" "$VOLUME_DIR"

# Conteneurs de bases projet : convention de nommage `{projet}_db` (compose de prod).
CONTAINERS=$(docker ps --format '{{.Names}}' --filter 'name=_db$')

if [[ -z "$CONTAINERS" ]]; then
    echo "Aucun conteneur de base projet (*_db) en cours d'exécution."
    exit 0
fi

FAILED=0
VOLUMES_SAVED=0
OFFSITE_FAILED=0

# $1 = fichier local, $2 = sous-dossier distant. Échec compté comme échec de
# la sauvegarde (visible dans l'onglet Maintenance), copie locale conservée.
offsite() {
    [[ -z "$RCLONE_REMOTE" ]] && return 0
    if ! timeout "$OFFSITE_TIMEOUT" rclone copyto "$1" "${RCLONE_REMOTE}/$2/$(basename "$1")" "${RCLONE_FLAGS[@]}"; then
        echo "  ✗ copie hors serveur échouée : $(basename "$1") (copie locale conservée)."
        OFFSITE_FAILED=$((OFFSITE_FAILED + 1))
        FAILED=$((FAILED + 1))
    fi
}
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
        offsite "$outfile" "$project"
        if [[ -n "$S3_BUCKET" ]]; then
            aws s3 cp "$outfile" "s3://${S3_BUCKET}/${project}/" || \
                echo "  ⚠ upload S3 échoué pour $project (dump local conservé)."
        fi
    else
        echo "  ✗ pg_dump a échoué pour $project."
        rm -f "$outfile"
        FAILED=$((FAILED + 1))
    fi

    # Volumes de fichiers du projet (audit f-ynd, 2026-11-23 — Chap 23) :
    # bug réel, les morceaux/pochettes des artistes de f-ynd (volume
    # f-ynd_media_data) n'étaient sauvegardés NULLE PART, seule la base
    # l'était. Tous les volumes nommés du projet (label Compose, jamais un
    # motif de nom qui déborderait sur un autre projet) sont archivés, sauf
    # celui de la base : déjà couvert par pg_dump, et une copie à chaud des
    # fichiers PostgreSQL ne serait pas cohérente. Montage en lecture seule.
    for volume in $(docker volume ls -q --filter "label=com.docker.compose.project=${project}"); do
        [[ "$volume" == *_db_data ]] && continue
        archive="${VOLUME_DIR}/${volume}_${DATE}.tar.gz"
        echo "  Archive du volume ${volume}..."
        if docker run --rm -v "${volume}:/data:ro" "$TAR_IMAGE" tar czf - -C /data . > "${archive}.part"; then
            mv "${archive}.part" "$archive"
            VOLUMES_SAVED=$((VOLUMES_SAVED + 1))
            offsite "$archive" "${project}/volumes"
            if [[ -n "$S3_BUCKET" ]]; then
                aws s3 cp "$archive" "s3://${S3_BUCKET}/${project}/volumes/" ||                     echo "  ⚠ upload S3 échoué pour ${volume} (archive locale conservée)."
            fi
        else
            echo "  ✗ archive du volume ${volume} échouée."
            rm -f "${archive}.part"
            FAILED=$((FAILED + 1))
        fi
    done
done

# Rotation : garder BACKUP_RETENTION jours de dumps locaux.
find "$BACKUP_DIR" -name "*.dump.gz" -mtime "+${BACKUP_RETENTION}" -delete
find "$VOLUME_DIR" -name "*.tar.gz" -mtime "+${VOLUME_RETENTION}" -delete
# Rotation distante, bornée au remote de sauvegarde (jamais au-delà).
if [[ -n "$RCLONE_REMOTE" ]]; then
    if ! timeout "$OFFSITE_TIMEOUT" rclone delete --min-age "${OFFSITE_RETENTION}d" "$RCLONE_REMOTE"; then
        echo "  ✗ rotation distante échouée."
        OFFSITE_FAILED=$((OFFSITE_FAILED + 1))
        FAILED=$((FAILED + 1))
    fi
fi

TOTAL=$(echo "$CONTAINERS" | wc -w)
if [[ $FAILED -gt 0 ]]; then
    STATUS="failure"
    SUMMARY="$FAILED échec(s) sur $TOTAL projet(s) (dont $OFFSITE_FAILED hors serveur)."
    echo "=== Sauvegarde flotte terminée avec $FAILED échec(s). ==="
else
    STATUS="success"
    SUMMARY="$TOTAL projet(s) sauvegardé(s), $VOLUMES_SAVED volume(s) de fichiers archivé(s), copie hors serveur : ${RCLONE_REMOTE:-AUCUNE}."
    echo "=== Sauvegarde flotte terminée. ==="
fi

# Reporting vers l'onglet Maintenance (Chap 23) — FLEET_URL/FLEET_REGISTER_TOKEN
# déjà exportés globalement par crontab.fleet (déclarés pour fleet-health.sh,
# cron les applique à tous les jobs suivants). Absents hors cron (lancement
# manuel) : on saute silencieusement, jamais d'échec sur ça (`|| true`) — un
# reporting raté ne doit jamais transformer une sauvegarde réussie en échec.
if [[ -n "${FLEET_URL:-}" ]]; then
    curl -fsS -X POST "${FLEET_URL}/api/fleet/maintenance/report" \
        -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"job\":\"backup-fleet\",\"status\":\"${STATUS}\",\"summary\":\"${SUMMARY}\"}" \
        >/dev/null || true
fi

[[ "$STATUS" == "failure" ]] && exit 1
exit 0
