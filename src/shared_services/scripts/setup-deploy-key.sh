#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/setup-deploy-key.sh — Clé de déploiement SSH dédiée
# à un projet, pour que le redeploy continu fonctionne sur un dépôt PRIVÉ.
# (Chap 26/27 — bug de prod réel, ai-qube 2026-09-23)
#
# Le premier push d'un projet créé via le wizard fonctionne déjà, avec
# FLEET_GITHUB_TOKEN embarqué dans l'URL juste le temps du push (jamais
# stocké ensuite, Chap 26). Mais le redeploy CONTINU (deploy-on-push.sh,
# cron) fait un simple `git pull` sans jeton — pour un dépôt PUBLIC ça
# marche tel quel (lecture anonyme), pour un dépôt PRIVÉ ça échoue toujours
# ("could not read Username for 'https://github.com'") tant qu'aucune
# authentification persistante n'est en place. Une clé de déploiement dédiée
# (lecture seule, scopée à CE dépôt) est la bonne réponse — jamais réutiliser
# FLEET_GITHUB_TOKEN pour ça, sa portée `repo` complète est bien plus large
# que nécessaire pour un simple pull.
#
# Usage : ./setup-deploy-key.sh <nom-projet> <owner>/<repo>
#   ex.  ./setup-deploy-key.sh ai-qube Nabil-Mabrouk/ai-qube
#
# Idempotent : rejouable sans risque (clé/alias déjà présents -> sautés).
# =============================================================================

set -euo pipefail

PROJECT="${1:?Usage: setup-deploy-key.sh <nom-projet> <owner>/<repo>}"
GITHUB_REPO="${2:?Usage: setup-deploy-key.sh <nom-projet> <owner>/<repo>}"

GITSKY_ROOT="${GITSKY_ROOT:-/opt/gitsky}"
PROJECT_DIR="${GITSKY_ROOT}/projects/${PROJECT}"
KEY_FILE="${HOME}/.ssh/${PROJECT}_deploy_key"
HOST_ALIAS="github.com-${PROJECT}"

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
    echo "✗ ${PROJECT_DIR} n'est pas un dépôt git — projet inexistant ?" >&2
    exit 1
fi

if [[ ! -f "$KEY_FILE" ]]; then
    ssh-keygen -t ed25519 -C "${PROJECT}-deploy" -f "$KEY_FILE" -N ""
fi

if ! grep -q "Host ${HOST_ALIAS}$" ~/.ssh/config 2>/dev/null; then
    cat >> ~/.ssh/config << EOF

Host ${HOST_ALIAS}
  HostName github.com
  IdentityFile ${KEY_FILE}
  IdentitiesOnly yes
EOF
    chmod 600 ~/.ssh/config
fi

if ! ssh -o BatchMode=yes -T "git@${HOST_ALIAS}" 2>&1 | grep -q "successfully authenticated"; then
    echo "✗ Clé pas encore autorisée sur GitHub." >&2
    echo "  Ajoute-la comme Deploy Key (lecture seule) sur ${GITHUB_REPO} :" >&2
    echo "  github.com/${GITHUB_REPO} -> Settings -> Deploy keys -> Add deploy key" >&2
    echo "" >&2
    cat "${KEY_FILE}.pub" >&2
    echo "" >&2
    echo "  Puis relance ce script." >&2
    exit 1
fi

git -C "$PROJECT_DIR" remote set-url origin "git@${HOST_ALIAS}:${GITHUB_REPO}.git"
git -C "$PROJECT_DIR" pull --ff-only

echo "✓ ${PROJECT} : redeploy continu opérationnel (clé dédiée, lecture seule)."
