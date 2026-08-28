#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/lifecycle-fleet.sh — Exécute les intentions de
# cycle de vie journalisées par le dashboard. (Chap 20/23, round sécurisation)
#
# Même patron que deploy-on-push.sh (Chap 26) : le dashboard n'a AUCUN accès
# Docker (Chap 26 §choix d'architecture, conteneur public-facing) — il ne
# fait que journaliser l'intention (POST /projects/{name}/stop|start|
# maintenance). CE script tourne sur l'hôte avec un accès Docker réel et
# exécute l'action, via GET /api/fleet/lifecycle/pending (curseur local
# STATE_FILE, même contrat texte brut que /deploys/pending).
#
# Actions :
#   stop              docker compose down
#   start             docker compose up -d (pas de --build : image déjà là)
#   maintenance       down du compose principal, puis up -d de
#                     docker-compose.maintenance.yml (page statique, MÊMES
#                     routes Traefik — les deux ne tournent jamais ensemble)
#   maintenance-clear l'inverse : down du compose de maintenance, puis
#                     up -d --build du compose principal
#
# Env requis :
#   FLEET_URL             — URL du dashboard
#   FLEET_REGISTER_TOKEN  — jeton machine-à-machine (X-Fleet-Token), même que
#                           deploy-on-push.sh / fleet-health.sh
# Env optionnel :
#   PROJECTS_DIR — racine des projets déployés (défaut /opt/gitsky/projects)
#   STATE_FILE   — curseur local (défaut /var/lib/gitsky/lifecycle-fleet.state)
# =============================================================================

set -euo pipefail

FLEET_URL="${FLEET_URL:?FLEET_URL requis}"
FLEET_REGISTER_TOKEN="${FLEET_REGISTER_TOKEN:?FLEET_REGISTER_TOKEN requis}"
PROJECTS_DIR="${PROJECTS_DIR:-/opt/gitsky/projects}"
STATE_FILE="${STATE_FILE:-/var/lib/gitsky/lifecycle-fleet.state}"

mkdir -p "$(dirname "$STATE_FILE")"
LAST_ID=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
[[ "$LAST_ID" =~ ^[0-9]+$ ]] || LAST_ID=0

report() {
    # $1=project $2=status $3=summary — reporting best-effort (`|| true`),
    # même raisonnement que deploy-on-push.sh : un échec de reporting ne
    # doit jamais faire échouer le script lui-même.
    curl -fsS -X POST "${FLEET_URL}/api/fleet/maintenance/report" \
        -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"job\":\"lifecycle\",\"status\":\"$2\",\"project\":\"$1\",\"summary\":\"$3\"}" \
        >/dev/null || true
}

apply_one() {
    local project="$1" action="$2"
    local dir="${PROJECTS_DIR}/${project}"

    if [[ ! -d "$dir" ]]; then
        echo "  ✗ ${project} : répertoire introuvable (${dir})."
        report "$project" "failure" "répertoire introuvable : ${dir}"
        return 1
    fi

    case "$action" in
        stop)
            echo "Arrêt de ${project}..."
            if (cd "$dir" && docker compose down); then
                echo "  ✓ ${project} arrêté."
                report "$project" "success" "arrêté"
            else
                echo "  ✗ ${project} : docker compose down a échoué."
                report "$project" "failure" "docker compose down a échoué"
                return 1
            fi
            ;;
        start)
            echo "Démarrage de ${project}..."
            if (cd "$dir" && docker compose up -d); then
                echo "  ✓ ${project} démarré."
                report "$project" "success" "démarré"
            else
                echo "  ✗ ${project} : docker compose up a échoué."
                report "$project" "failure" "docker compose up a échoué"
                return 1
            fi
            ;;
        maintenance)
            echo "Passage en maintenance de ${project}..."
            if (cd "$dir" \
                    && docker compose down \
                    && docker compose -f docker-compose.maintenance.yml up -d); then
                echo "  ✓ ${project} en maintenance."
                report "$project" "success" "maintenance activée"
            else
                echo "  ✗ ${project} : passage en maintenance a échoué."
                report "$project" "failure" "passage en maintenance a échoué"
                return 1
            fi
            ;;
        maintenance-clear)
            echo "Sortie de maintenance de ${project}..."
            if (cd "$dir" \
                    && docker compose -f docker-compose.maintenance.yml down \
                    && docker compose up -d); then
                echo "  ✓ ${project} sorti de maintenance."
                report "$project" "success" "maintenance désactivée"
            else
                echo "  ✗ ${project} : sortie de maintenance a échoué."
                report "$project" "failure" "sortie de maintenance a échoué"
                return 1
            fi
            ;;
        *)
            echo "  ✗ ${project} : action inconnue « ${action} »."
            report "$project" "failure" "action inconnue : ${action}"
            return 1
            ;;
    esac
}

PENDING=$(curl -fsS "${FLEET_URL}/api/fleet/lifecycle/pending?since_id=${LAST_ID}" \
    -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}")

if [[ -z "$PENDING" ]]; then
    exit 0
fi

FAILED=0
while IFS=$'\t' read -r id project action; do
    [[ -z "$id" ]] && continue
    apply_one "$project" "$action" || FAILED=$((FAILED + 1))
    LAST_ID="$id"
done <<< "$PENDING"

# Le curseur avance même en cas d'échec — même logique que deploy-on-push.sh :
# un projet cassé ne doit pas bloquer indéfiniment les actions suivantes.
echo "$LAST_ID" > "$STATE_FILE"

[[ $FAILED -gt 0 ]] && exit 1
exit 0
