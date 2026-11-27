#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/llm-proxy-keys.sh — Base et jetons projet du
# llm-proxy partagé (Chap 18 §4).
#
#   llm-proxy-keys.sh init-db
#       Crée (idempotent) le rôle + la base postgres "litellm" utilisés par
#       LiteLLM pour ses jetons virtuels, budgets et spend logs. Génère
#       LITELLM_DB_PASSWORD dans shared_services/.env s'il est absent/vide,
#       et réaligne TOUJOURS le mot de passe du rôle sur cette valeur (même
#       classe de dérive que l'incident postgres du 2026-08-28).
#
#   llm-proxy-keys.sh create-key <projet> <budget_usd> <modele1,modele2,...>
#       Émet un jeton propre au projet (key_alias=<projet>, max_budget,
#       budget_duration=$BUDGET_DURATION défaut 1d, allowlist de modèles
#       OBLIGATOIRE) et l'écrit directement dans
#       $PROJECTS_DIR/<projet>/.env.local (LLM_PROXY_URL + LLM_PROXY_TOKEN),
#       en remplaçant toute valeur précédente (ex. la clé maître).
#
#   llm-proxy-keys.sh update-key <projet> <budget_usd> <modele1,modele2,...>
#       Change budget + allowlist du jeton EXISTANT du projet (lu dans son
#       .env.local) via /key/update — le jeton lui-même ne change pas, aucun
#       redémarrage du projet nécessaire.
#
# Garanties de sécurité :
#   - le jeton émis n'est JAMAIS affiché (ni stdout ni stderr) : il ne doit
#     transiter ni par un terminal partagé, ni par un chat, ni par un agent ;
#   - la clé maître n'apparaît jamais dans un argv : le code python tourne
#     DANS le conteneur llm-proxy et la lit dans l'env du conteneur ;
#   - le mot de passe de la base passe par stdin (SQL), jamais par argv.
#
# Après create-key : recréer les conteneurs du projet pour recharger son env
#   cd $PROJECTS_DIR/<projet> && docker compose up -d
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED_DIR="${SHARED_DIR:-$(dirname "$SCRIPT_DIR")}"
PROJECTS_DIR="${PROJECTS_DIR:-/opt/gitsky/projects}"
BUDGET_DURATION="${BUDGET_DURATION:-1d}"
PROXY_URL="${PROXY_URL:-http://llm-proxy:4000}"

usage() {
    echo "Usage : $0 init-db" >&2
    echo "        $0 create-key <projet> <budget_usd> <modele1,modele2,...>" >&2
    echo "        $0 update-key <projet> <budget_usd> <modele1,modele2,...>" >&2
    echo "        $0 delete-key <projet>   (révoque la clé, avant suppression du projet)" >&2
    exit 2
}

random_hex() {
    head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'
}

init_db() {
    local env_file="${SHARED_DIR}/.env"
    touch "$env_file"
    local pw
    pw="$(grep -E '^LITELLM_DB_PASSWORD=' "$env_file" | head -n1 | cut -d= -f2- || true)"
    if [[ -z "$pw" ]]; then
        pw="$(random_hex)"
        if grep -qE '^LITELLM_DB_PASSWORD=$' "$env_file"; then
            sed -i "s|^LITELLM_DB_PASSWORD=$|LITELLM_DB_PASSWORD=${pw}|" "$env_file"
        else
            printf 'LITELLM_DB_PASSWORD=%s\n' "$pw" >> "$env_file"
        fi
        echo "LITELLM_DB_PASSWORD généré dans ${env_file}."
    fi
    if [[ ! "$pw" =~ ^[A-Za-z0-9]+$ ]]; then
        echo "✗ LITELLM_DB_PASSWORD contient des caractères non alphanumériques" >&2
        echo "  (casserait DATABASE_URL) — vider la ligne et relancer init-db." >&2
        exit 1
    fi

    cd "$SHARED_DIR"
    docker compose exec -T postgres psql -U postgres -v ON_ERROR_STOP=1 -q <<SQL
SELECT 'CREATE ROLE litellm LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'litellm')\gexec
ALTER ROLE litellm WITH LOGIN PASSWORD '${pw}';
SELECT 'CREATE DATABASE litellm OWNER litellm' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec
SQL
    echo "✓ Rôle et base 'litellm' prêts. Redémarrer le proxy : docker compose up -d llm-proxy"
}

validate_args() {
    local project="$1" budget="$2" models="$3"
    [[ "$project" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "✗ nom de projet invalide : '${project}'" >&2; exit 1; }
    [[ "$budget" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "✗ budget invalide (USD, ex. 12 ou 12.5) : '${budget}'" >&2; exit 1; }
    # Allowlist obligatoire : sans elle, le jeton aurait accès à tout le
    # catalogue du proxy (Opus compris).
    [[ "$models" =~ ^[A-Za-z0-9._-]+(,[A-Za-z0-9._-]+)*$ ]] || { echo "✗ liste de modèles invalide ou vide : '${models}'" >&2; exit 1; }
    [[ "$BUDGET_DURATION" =~ ^[0-9]+(s|m|h|d|mo)$ ]] || { echo "✗ BUDGET_DURATION invalide : '${BUDGET_DURATION}'" >&2; exit 1; }
    [[ -d "${PROJECTS_DIR}/${project}" ]] || { echo "✗ projet introuvable : ${PROJECTS_DIR}/${project}" >&2; exit 1; }
}

update_key() {
    local project="${1:-}" budget="${2:-}" models="${3:-}"
    validate_args "$project" "$budget" "$models"
    local env_file="${PROJECTS_DIR}/${project}/.env.local"
    local token
    token="$(grep -E '^LLM_PROXY_TOKEN=' "$env_file" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    [[ -n "$token" ]] || { echo "✗ aucun LLM_PROXY_TOKEN dans ${env_file} — utiliser create-key." >&2; exit 1; }

    cd "$SHARED_DIR"
    # Jeton du projet via stdin (jamais argv) ; code python via -c (non secret).
    printf '%s' "$token" | docker compose exec -T llm-proxy python -c '
import json, os, sys, urllib.error, urllib.request
budget, duration, models = sys.argv[1:4]
body = {"key": sys.stdin.read().strip(), "max_budget": float(budget),
        "budget_duration": duration, "models": [m for m in models.split(",") if m]}
req = urllib.request.Request("http://localhost:4000/key/update", data=json.dumps(body).encode(),
    headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"], "Content-Type": "application/json"},
    method="POST")
try:
    urllib.request.urlopen(req, timeout=30).read()
except urllib.error.HTTPError as exc:
    print(f"/key/update HTTP {exc.code}: {exc.read().decode()[:500]}", file=sys.stderr)
    sys.exit(1)
' "$budget" "$BUDGET_DURATION" "$models" >/dev/null || { echo "✗ mise à jour refusée par le proxy (voir ci-dessus)." >&2; exit 1; }
    echo "✓ Jeton '${project}' mis à jour (budget ${budget} USD / ${BUDGET_DURATION}, modèles : ${models})."
}

delete_key() {
    local project="${1:-}"
    [[ "$project" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "✗ nom de projet invalide : '${project}'" >&2; exit 1; }
    local env_file="${PROJECTS_DIR}/${project}/.env.local"
    local token
    token="$(grep -E '^LLM_PROXY_TOKEN=' "$env_file" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    [[ -n "$token" ]] || { echo "✗ aucun LLM_PROXY_TOKEN dans ${env_file} — rien à révoquer." >&2; exit 1; }

    cd "$SHARED_DIR"
    # Jeton du projet via stdin (jamais argv) ; code python via -c (non secret).
    printf '%s' "$token" | docker compose exec -T llm-proxy python -c '
import json, os, sys, urllib.error, urllib.request
body = {"keys": [sys.stdin.read().strip()]}
req = urllib.request.Request("http://localhost:4000/key/delete", data=json.dumps(body).encode(),
    headers={"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"], "Content-Type": "application/json"},
    method="POST")
try:
    urllib.request.urlopen(req, timeout=30).read()
except urllib.error.HTTPError as exc:
    print(f"/key/delete HTTP {exc.code}: {exc.read().decode()[:500]}", file=sys.stderr)
    sys.exit(1)
' >/dev/null || { echo "✗ révocation refusée par le proxy (voir ci-dessus) — .env.local inchangé." >&2; exit 1; }
    # sed -i garde les droits du fichier (600).
    sed -i '/^LLM_PROXY_TOKEN=/d' "$env_file"
    echo "✓ Jeton '${project}' révoqué dans le proxy et retiré de ${env_file}."
}

create_key() {
    local project="${1:-}" budget="${2:-}" models="${3:-}"
    validate_args "$project" "$budget" "$models"
    local project_dir="${PROJECTS_DIR}/${project}"

    cd "$SHARED_DIR"
    local key
    key="$(docker compose exec -T llm-proxy python - "$project" "$budget" "$BUDGET_DURATION" "$models" <<'PY'
import json, os, sys, urllib.error, urllib.request

alias, budget, duration, models = sys.argv[1:5]
body = {
    "key_alias": alias,
    "max_budget": float(budget),
    "budget_duration": duration,
    "models": [m for m in models.split(",") if m],
    "metadata": {"project": alias},
}
req = urllib.request.Request(
    "http://localhost:4000/key/generate",
    data=json.dumps(body).encode(),
    headers={
        "Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(json.load(resp)["key"])
except urllib.error.HTTPError as exc:
    sys.stderr.write(f"/key/generate HTTP {exc.code}: {exc.read().decode()[:500]}\n")
    sys.exit(1)
PY
)" || { echo "✗ création du jeton refusée par le proxy (voir ci-dessus)." >&2; exit 1; }
    key="$(printf '%s' "$key" | tr -d '\r\n')"
    if [[ ! "$key" =~ ^sk-[A-Za-z0-9_-]+$ ]]; then
        echo "✗ réponse inattendue du proxy (pas un jeton sk-...) — .env.local inchangé." >&2
        exit 1
    fi

    local env_file="${project_dir}/.env.local"
    if [[ ! -f "$env_file" ]]; then
        touch "$env_file"
        chmod 600 "$env_file"
    fi
    local tmp
    tmp="$(mktemp "${env_file}.XXXXXX")"
    grep -vE '^(LLM_PROXY_URL|LLM_PROXY_TOKEN)=' "$env_file" > "$tmp" || true
    printf 'LLM_PROXY_URL=%s\nLLM_PROXY_TOKEN=%s\n' "$PROXY_URL" "$key" >> "$tmp"
    # cat > plutôt que mv : conserve le propriétaire et les droits (600) du fichier.
    cat "$tmp" > "$env_file"
    rm -f "$tmp"

    echo "✓ Jeton '${project}' créé (budget ${budget} USD / ${BUDGET_DURATION}, modèles : ${models})."
    echo "  Écrit dans ${env_file} (non affiché). Recharger le projet :"
    echo "  cd ${project_dir} && docker compose up -d"
}

case "${1:-}" in
    init-db) init_db ;;
    create-key) shift; create_key "$@" ;;
    update-key) shift; update_key "$@" ;;
    delete-key) shift; delete_key "$@" ;;
    *) usage ;;
esac
