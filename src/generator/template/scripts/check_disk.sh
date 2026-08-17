#!/usr/bin/env bash
# =============================================================================
# scripts/check_disk.sh — Vérifie l'espace disque, alerte au-delà d'un seuil.
# (Chap 23 §3.2) Le disque plein est la panne n°1 en production.
#
# Codes de sortie : 0 = OK/avertissement, 1 = seuil CRITIQUE dépassé.
# Config .env.backup : ALERT_EMAIL, THRESHOLD_WARN, THRESHOLD_CRIT.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env.backup"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

THRESHOLD_WARN="${THRESHOLD_WARN:-70}"
THRESHOLD_CRIT="${THRESHOLD_CRIT:-85}"
ALERT_EMAIL="${ALERT_EMAIL:-}"
CRITICAL=0

check_path() {
    local path="$1" label="$2" usage
    usage=$(df "$path" 2>/dev/null | awk 'NR==2 {sub(/%/,"",$5); print $5}')
    [[ -z "$usage" ]] && return 0

    if [[ "$usage" -ge "$THRESHOLD_CRIT" ]]; then
        echo "✗ CRITIQUE : $label à ${usage}% (seuil ${THRESHOLD_CRIT}%)"
        [[ -n "$ALERT_EMAIL" ]] && echo "Disque $label à ${usage}% sur $(hostname)" \
            | mail -s "[GitSky] ALERTE CRITIQUE: disque presque plein" "$ALERT_EMAIL" 2>/dev/null || true
        CRITICAL=1
    elif [[ "$usage" -ge "$THRESHOLD_WARN" ]]; then
        echo "⚠ ATTENTION : $label à ${usage}% (seuil ${THRESHOLD_WARN}%)"
        [[ -n "$ALERT_EMAIL" ]] && echo "Disque $label à ${usage}% sur $(hostname)" \
            | mail -s "[GitSky] ATTENTION: disque $label à ${usage}%" "$ALERT_EMAIL" 2>/dev/null || true
    else
        echo "✓ $label : ${usage}% utilisé"
    fi
}

echo "=== Vérification de l'espace disque - $(date) ==="
check_path "/"        "Disque principal"
check_path "/backups" "Disque sauvegardes"

exit $CRITICAL
