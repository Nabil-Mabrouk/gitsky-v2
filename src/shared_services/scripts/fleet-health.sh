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
#   FLEET_API    — URL du dashboard (ex. https://api.mystudio.com)
#   FLEET_TOKEN  — jeton admin (Bearer) pour /projects/health-sweep
#   STATE_FILE   — fichier d'état (défaut : /var/lib/gitsky/fleet-health.state)
# =============================================================================

set -euo pipefail

FLEET_API="${FLEET_API:?FLEET_API requis}"
FLEET_TOKEN="${FLEET_TOKEN:?FLEET_TOKEN requis}"
STATE_FILE="${STATE_FILE:-/var/lib/gitsky/fleet-health.state}"
mkdir -p "$(dirname "$STATE_FILE")"
touch "$STATE_FILE"

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Backends projet : convention `{projet}_backend` (compose de prod).
CONTAINERS=$(docker ps --format '{{.Names}}' --filter 'name=_backend$')

# Met à jour l'état : succès -> NOW, sinon on conserve le dernier succès connu.
for container in $CONTAINERS; do
    project="${container%_backend}"
    if docker exec "$container" \
            sh -c 'curl -fsS http://localhost:8000/health >/dev/null 2>&1'; then
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

curl -fsS -X POST "${FLEET_API}/api/fleet/projects/health-sweep" \
    -H "Authorization: Bearer ${FLEET_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$payload"
