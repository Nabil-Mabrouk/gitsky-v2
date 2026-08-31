#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/update-geoip-db.sh — Rafraîchit la base MaxMind
# GeoLite2-City partagée par le service geoip (Chap 13/18).
#
# Invoque le service one-shot `geoipupdate` (image officielle
# maxmindinc/geoipupdate) via `docker compose run --rm`, jamais `up` (qui ne
# gère pas correctement un conteneur one-shot). `--profile geoipupdate` est
# nécessaire : ce service est volontairement exclu d'un `docker compose up -d`
# normal (sinon chaque redéploiement de shared_services déclencherait un
# appel MaxMind superflu, docker-compose.yml).
#
# MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY viennent de shared_services/.env
# (jamais committé) — docker compose les lit automatiquement depuis ce
# fichier quand la commande est exécutée depuis shared_services/, comme tous
# les autres scripts de ce dossier.
# =============================================================================

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Mise à jour de la base GeoIP (geoipupdate)..."
if docker compose --profile geoipupdate run --rm geoipupdate; then
    STATUS="success"
    SUMMARY="Base GeoIP mise à jour."
    echo "=== Mise à jour GeoIP terminée. ==="
else
    STATUS="failure"
    SUMMARY="Échec de geoipupdate (voir logs)."
    echo "✗ geoipupdate a échoué."
fi

# geoip_service/main.py ouvre son Reader() une seule fois au démarrage,
# jamais à chaud — sans ce restart, la mise à jour resterait invisible du
# service jusqu'au prochain événement sans rapport qui le redémarre.
docker compose restart geoip || true

# Reporting vers l'onglet Maintenance (Chap 23), même mécanisme que
# backup-fleet.sh — silencieux si FLEET_URL absent (lancement manuel).
if [[ -n "${FLEET_URL:-}" ]]; then
    curl -fsS -X POST "${FLEET_URL}/api/fleet/maintenance/report" \
        -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"job\":\"update-geoip-db\",\"status\":\"${STATUS}\",\"summary\":\"${SUMMARY}\"}" \
        >/dev/null || true
fi

[[ "$STATUS" == "failure" ]] && exit 1
exit 0
