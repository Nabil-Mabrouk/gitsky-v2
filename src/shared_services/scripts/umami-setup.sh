#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/umami-setup.sh — Base et secrets d'Umami (Chap 18 §8).
#
#   umami-setup.sh init
#       Génère dans shared_services/.env UMAMI_DB_PASSWORD et UMAMI_APP_SECRET
#       s'ils sont absents ou vides — JAMAIS réécrits ensuite : changer
#       APP_SECRET déconnecte tout le monde et réinitialise les identifiants
#       anonymes de visite. Crée (idempotent) le rôle + la base "umami" sur le
#       postgres partagé et réaligne le mot de passe du rôle sur .env.
#       Mot de passe passé par stdin (SQL), jamais par argv ni affiché.
#
# Ensuite : docker compose up -d umami
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="${SHARED_DIR:-$(dirname "$SCRIPT_DIR")}"

usage() {
    echo "Usage : $0 init" >&2
    exit 2
}

random_hex() {
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
}

# $1 = fichier .env, $2 = clé. Génère une valeur si absente ou vide, puis la
# renvoie sur stdout (capturée par l'appelant, jamais affichée).
ensure_secret() {
    local env_file="$1" key="$2" value
    value="$(grep -E "^${key}=" "$env_file" | head -n1 | cut -d= -f2- || true)"
    if [[ -z "$value" ]]; then
        value="$(random_hex)"
        if grep -qE "^${key}=$" "$env_file"; then
            sed -i "s|^${key}=$|${key}=${value}|" "$env_file"
        else
            printf '%s=%s\n' "$key" "$value" >> "$env_file"
        fi
        echo "${key} généré dans ${env_file}." >&2
    fi
    printf '%s' "$value"
}

init() {
    local env_file="${SHARED_DIR}/.env"
    touch "$env_file"
    local pw
    pw="$(ensure_secret "$env_file" UMAMI_DB_PASSWORD)"
    ensure_secret "$env_file" UMAMI_APP_SECRET >/dev/null
    if [[ ! "$pw" =~ ^[A-Za-z0-9]+$ ]]; then
        echo "✗ UMAMI_DB_PASSWORD contient des caractères non alphanumériques" >&2
        echo "  (casserait DATABASE_URL) — vider la ligne et relancer init." >&2
        exit 1
    fi

    cd "$SHARED_DIR"
    docker compose exec -T postgres psql -U postgres -v ON_ERROR_STOP=1 -q <<SQL
SELECT 'CREATE ROLE umami LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'umami')\gexec
ALTER ROLE umami WITH LOGIN PASSWORD '${pw}';
SELECT 'CREATE DATABASE umami OWNER umami' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'umami')\gexec
SQL
    echo "✓ Rôle et base 'umami' prêts. Démarrer : docker compose up -d umami"
}

case "${1:-}" in
    init) init ;;
    *) usage ;;
esac
