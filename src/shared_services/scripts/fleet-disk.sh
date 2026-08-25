#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/fleet-disk.sh — Jauge disque consolidée par projet.
# (Chap 23 §« Alerte Disque Consolidée »)
#
# Sur un VPS mutualisé, un seul projet qui log trop peut remplir le disque.
# `docker system df -v` attribue l'espace par conteneur/volume — bien plus
# rapide que de fouiller `du -sh /var/lib/docker/*` pour trouver le coupable.
# =============================================================================

set -euo pipefail

echo "=== Espace disque global - $(date) ==="
df -h / /backups 2>/dev/null || df -h /

echo ""
echo "=== Répartition Docker (images / conteneurs / volumes) ==="
docker system df

echo ""
echo "=== Volumes par projet (les plus gros d'abord) ==="
# Les volumes de bases projet sont nommés d'après leur projet (db_data scopé).
docker system df -v --format '{{ json .Volumes }}' 2>/dev/null \
    | tr ',' '\n' | grep -iE 'db_data|_db' || \
    docker system df -v

# Reporting vers l'onglet Maintenance (Chap 23) — purement informatif, ce
# script n'a pas de seuil d'échec, toujours "success". FLEET_URL/
# FLEET_REGISTER_TOKEN déjà exportés globalement par crontab.fleet ; absents
# hors cron, on saute silencieusement (`|| true`).
DISK_PCT=$(df -h / | awk 'NR==2{print $5}')
if [[ -n "${FLEET_URL:-}" ]]; then
    curl -fsS -X POST "${FLEET_URL}/api/fleet/maintenance/report" \
        -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"job\":\"disk-check\",\"status\":\"success\",\"summary\":\"Disque / : ${DISK_PCT}\"}" \
        >/dev/null || true
fi
