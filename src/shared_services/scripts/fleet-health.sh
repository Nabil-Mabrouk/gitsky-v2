#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/fleet-health.sh — Poller de disponibilité de flotte.
# (Chap 23 §« Monitoring de Disponibilité de Flotte »)
#
# Cron 60 s : interroge /health de chaque backend projet, tient à jour l'horaire
# du dernier succès (fichier d'état), puis POSTe la carte au fleet dashboard.
# C'est CE DERNIER qui décide (health_monitor.py) : muet > 5 min -> alerte
# deployment_failed. La décision est en Python (testée) ; ici, uniquement l'I/O.
#
# Env requis :
#   FLEET_URL             — URL du dashboard (ex. https://api.mystudio.com)
#   FLEET_REGISTER_TOKEN  — jeton machine-à-machine (X-Fleet-Token) partagé
#                           avec le générateur (register_fleet.py) pour
#                           /projects/register ET /projects/health-sweep —
#                           ce n'est PAS un JWT admin, health-sweep est un
#                           script non-interactif, pas une session opérateur.
#   STATE_FILE            — fichier d'état (défaut : /var/lib/gitsky/fleet-health.state)
# =============================================================================

set -euo pipefail

FLEET_URL="${FLEET_URL:?FLEET_URL requis}"
FLEET_REGISTER_TOKEN="${FLEET_REGISTER_TOKEN:?FLEET_REGISTER_TOKEN requis}"
STATE_FILE="${STATE_FILE:-/var/lib/gitsky/fleet-health.state}"
mkdir -p "$(dirname "$STATE_FILE")"
touch "$STATE_FILE"

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Backends projet : convention `{projet}_backend` (compose de prod).
CONTAINERS=$(docker ps --format '{{.Names}}' --filter 'name=_backend$')

# Met à jour l'état : succès -> NOW, sinon on conserve le dernier succès connu.
for container in $CONTAINERS; do
    project="${container%_backend}"
    # Python, pas curl : les images backend GitSky (Chap 21) n'installent
    # délibérément pas curl (le HEALTHCHECK du Dockerfile sonde déjà en
    # Python) — un `docker exec ... curl` échoue silencieusement partout
    # ("curl: not found", code 127), l'état ne se met jamais à jour, et
    # tout projet finit par être déclaré `deployment_failed` après 5 min
    # sans qu'aucun ne le soit réellement (bug de prod réel, trouvé en
    # vérifiant le monitoring après un redéploiement de flotte).
    if docker exec "$container" python -c '
import sys, urllib.request
try:
    sys.exit(0 if urllib.request.urlopen("http://localhost:8000/health", timeout=4).status == 200 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1; then
        grep -v "^${project}=" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
        echo "${project}=${NOW}" >> "${STATE_FILE}.tmp"
        mv "${STATE_FILE}.tmp" "$STATE_FILE"
    fi
done

# Construit la carte JSON last_success à partir de l'état.
entries=""
while IFS='=' read -r project ts; do
    [[ -z "$project" ]] && continue
    entries="${entries:+$entries,}\"${project}\":\"${ts}\""
done < "$STATE_FILE"

payload="{\"last_success\":{${entries}},\"now\":\"${NOW}\"}"

curl -fsS -X POST "${FLEET_URL}/api/fleet/projects/health-sweep" \
    -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$payload"
