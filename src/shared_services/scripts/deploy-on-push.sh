#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/deploy-on-push.sh — Redeploy déclenché par push GitHub.
# (Chap 26 §Pipeline de déploiement)
#
# Cron court (1-2 min) : interroge GET /api/fleet/deploys/pending (événements
# deploy_triggered pas encore traités par CE script — curseur local dans
# STATE_FILE), puis pour chaque projet en attente : git pull --ff-only +
# (optionnel) copier update + docker compose up -d --build + vérification
# /health, et reporte le résultat à /api/fleet/maintenance/report (job="deploy").
#
# Le webhook (POST /api/fleet/webhooks/github/{name}, Chap 26) ne fait QUE
# vérifier la signature et journaliser un deploy_triggered filtré sur la
# branche de déploiement — c'est CE script, tournant sur l'hôte avec un accès
# réel à Docker, qui exécute le redeploy. Le conteneur dashboard n'a lui aucun
# accès Docker : la surface d'attaque d'un conteneur public-facing reste
# minimale (choix d'architecture Chap 26, alternative écartée : socket Docker
# monté dans le conteneur dashboard).
#
# Env requis :
#   FLEET_URL             — URL du dashboard
#   FLEET_REGISTER_TOKEN  — jeton machine-à-machine (X-Fleet-Token), même que
#                           fleet-health.sh / backup-fleet.sh
# Env optionnel :
#   PROJECTS_DIR       — racine des projets déployés (défaut /opt/gitsky/projects)
#   STATE_FILE         — curseur local (défaut /var/lib/gitsky/deploy-on-push.state)
#   RUN_COPIER_UPDATE  — "1" pour lancer `copier update --trust` avant le build
#                        (défaut désactivé : peut demander une résolution de
#                        conflit interactive, pas sûr sans supervision, sous cron)
# =============================================================================

set -euo pipefail

FLEET_URL="${FLEET_URL:?FLEET_URL requis}"
FLEET_REGISTER_TOKEN="${FLEET_REGISTER_TOKEN:?FLEET_REGISTER_TOKEN requis}"
PROJECTS_DIR="${PROJECTS_DIR:-/opt/gitsky/projects}"
STATE_FILE="${STATE_FILE:-/var/lib/gitsky/deploy-on-push.state}"
RUN_COPIER_UPDATE="${RUN_COPIER_UPDATE:-0}"

mkdir -p "$(dirname "$STATE_FILE")"
LAST_ID=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
[[ "$LAST_ID" =~ ^[0-9]+$ ]] || LAST_ID=0

report() {
    # $1=project $2=status $3=summary — reporting best-effort (`|| true`) :
    # un échec de reporting ne doit jamais faire échouer le script lui-même,
    # même raisonnement que backup-fleet.sh / fleet-disk.sh.
    curl -fsS -X POST "${FLEET_URL}/api/fleet/maintenance/report" \
        -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"job\":\"deploy\",\"status\":\"$2\",\"project\":\"$1\",\"summary\":\"$3\"}" \
        >/dev/null || true
}

deploy_one() {
    local project="$1"
    local dir="${PROJECTS_DIR}/${project}"

    if [[ ! -d "$dir" ]]; then
        echo "  ✗ ${project} : répertoire introuvable (${dir})."
        report "$project" "failure" "répertoire introuvable : ${dir}"
        return 1
    fi

    echo "Redeploy de ${project}..."
    # --ff-only : jamais de merge/rebase automatique. Le serveur ne fait que
    # pull (règle établie ce trimestre) — un historique divergent doit faire
    # échouer bruyamment ce script, pas être résolu en silence.
    if ! (
        cd "$dir" \
            && git pull --ff-only \
            && { [[ "$RUN_COPIER_UPDATE" != "1" ]] || copier update --trust --defaults; } \
            && docker compose up -d --build
    ); then
        echo "  ✗ ${project} : git pull / copier update / docker compose up a échoué."
        report "$project" "failure" "git pull / docker compose up a échoué"
        return 1
    fi

    # Convention `{projet}_backend` (compose de prod), même que fleet-health.sh.
    # Python, pas curl : les images backend GitSky (Chap 21) n'installent
    # délibérément pas curl (le HEALTHCHECK du Dockerfile sonde déjà en
    # Python) — un `docker exec ... curl` échouait donc TOUJOURS en silence
    # (127, "not found"), quel que soit le succès réel du redeploy. Même bug,
    # même fix que fleet-health.sh (trouvé indépendamment ici en vérifiant
    # un vrai cycle de redeploy bout en bout).
    if docker exec "${project}_backend" python -c '
import sys, urllib.request
try:
    sys.exit(0 if urllib.request.urlopen("http://localhost:8000/health", timeout=4).status == 200 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1; then
        echo "  ✓ ${project} redéployé, /health répond."
        report "$project" "success" "redeploy ok"
        return 0
    fi
    echo "  ✗ ${project} : redeploy fait mais /health ne répond pas."
    report "$project" "failure" "redeploy fait mais /health ne répond pas"
    return 1
}

PENDING=$(curl -fsS "${FLEET_URL}/api/fleet/deploys/pending?since_id=${LAST_ID}" \
    -H "X-Fleet-Token: ${FLEET_REGISTER_TOKEN}")

if [[ -z "$PENDING" ]]; then
    exit 0
fi

FAILED=0
while IFS=$'\t' read -r id project; do
    [[ -z "$id" ]] && continue
    deploy_one "$project" || FAILED=$((FAILED + 1))
    LAST_ID="$id"
done <<< "$PENDING"

# Le curseur avance même en cas d'échec : un projet cassé ne doit pas bloquer
# indéfiniment les déploiements suivants — même logique que le webhook, qui ne
# rejoue jamais un event_type deploy_triggered plus ancien après un échec.
echo "$LAST_ID" > "$STATE_FILE"

[[ $FAILED -gt 0 ]] && exit 1
exit 0
