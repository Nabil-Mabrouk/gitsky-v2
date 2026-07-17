#!/usr/bin/env bash
# =============================================================================
# scripts/check_errors.sh — Alerte sur un taux anormal d'erreurs 5xx.
# (Chap 23 §4.1) Analyse les logs Traefik sur une fenêtre glissante.
#
# Traefik est un service PARTAGÉ de la flotte (Chap 18) : son conteneur n'est
# pas scopé au projet — d'où TRAEFIK_CONTAINER (défaut : traefik).
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env.backup"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

TRAEFIK_CONTAINER="${TRAEFIK_CONTAINER:-traefik}"
WINDOW_MINUTES="${WINDOW_MINUTES:-60}"
THRESHOLD_5XX="${THRESHOLD_5XX:-10}"
ALERT_EMAIL="${ALERT_EMAIL:-}"

ERROR_COUNT=$(docker logs "$TRAEFIK_CONTAINER" --since "${WINDOW_MINUTES}m" 2>&1 \
    | grep -c '"status":5' || true)

if [[ "$ERROR_COUNT" -ge "$THRESHOLD_5XX" ]]; then
    echo "✗ ALERTE : $ERROR_COUNT erreurs 5xx dans la dernière heure (seuil $THRESHOLD_5XX)."
    [[ -n "$ALERT_EMAIL" ]] && echo "$ERROR_COUNT erreurs 5xx en ${WINDOW_MINUTES}min sur $(hostname)" \
        | mail -s "[GitSky] Taux d'erreurs anormal" "$ALERT_EMAIL" 2>/dev/null || true
    exit 1
fi
echo "✓ Taux d'erreurs normal : $ERROR_COUNT erreur(s) 5xx (seuil $THRESHOLD_5XX)."
