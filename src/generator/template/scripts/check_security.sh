#!/usr/bin/env bash
# =============================================================================
# scripts/check_security.sh — Audit rapide de la surface d'exposition réseau.
# (Chap 23 §2.3 — adapté GitSky : conteneur par projet)
#
# Config .env.backup : POSTGRES_CONTAINER. Sort en erreur si un problème
# CRITIQUE est détecté (db exposée, .env tracké par git).
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env.backup"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-gitsky_db}"

echo "=== Audit de sécurité réseau ($POSTGRES_CONTAINER) ==="
ERRORS=0

# 1. PostgreSQL ne doit pas être publié sur 0.0.0.0 (compose de prod : aucun ports:).
PG_BINDING=$(docker inspect "$POSTGRES_CONTAINER" \
    --format='{{range $p, $b := .NetworkSettings.Ports}}{{$p}} -> {{$b}}{{end}}' \
    2>/dev/null || echo "")
if echo "$PG_BINDING" | grep -q "0.0.0.0"; then
    echo "✗ CRITIQUE : PostgreSQL exposé publiquement ! ($PG_BINDING)"
    ERRORS=$((ERRORS + 1))
else
    echo "✓ PostgreSQL non exposé publiquement."
fi

# 2. Les fichiers .env ne doivent jamais être suivis par git.
for secret in .env .env.backup .env.prod; do
    if git -C "$PROJECT_DIR" ls-files --error-unmatch "$secret" >/dev/null 2>&1; then
        echo "✗ CRITIQUE : $secret est suivi par git !"
        ERRORS=$((ERRORS + 1))
    fi
done

# 3. Permissions des fichiers de secrets (attendu : 600 ou 400).
for secret in .env .env.backup .env.prod; do
    path="${PROJECT_DIR}/${secret}"
    if [[ -f "$path" ]]; then
        PERMS=$(stat -c "%a" "$path" 2>/dev/null || echo "???")
        if [[ "$PERMS" != "600" && "$PERMS" != "400" ]]; then
            echo "✗ ATTENTION : $secret permissions trop larges ($PERMS). chmod 600 recommandé."
        else
            echo "✓ Permissions $secret : OK ($PERMS)"
        fi
    fi
done

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "=== $ERRORS problème(s) critique(s). Action immédiate requise. ==="
    exit 1
fi
echo "=== Audit terminé. Aucun problème critique. ==="
