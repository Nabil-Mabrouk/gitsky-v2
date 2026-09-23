#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/bootstrap-fleet.sh — Bootstrap d'une flotte GitSky
# sur un serveur fraîchement durci (harden-server.sh).
# (Chap 18/22/27 — remplace l'esquisse "bootstrap-fleet.sh" du Chap 22, qui
# décrivait une arborescence /opt/mystudio/shared-services/<service>/ jamais
# implémentée : la vraie structure est UN docker-compose.yml pour les 5
# services, /opt/gitsky/... comme racine, ce script l'assume.)
#
# Précondition NON automatisée, volontairement : une clé de déploiement
# GitHub (lecture seule) déjà ajoutée au dépôt monorepo — ajouter une clé de
# déploiement se fait via l'UI GitHub, pas d'API stable/scriptable sans un
# jeton à portée plus large que nécessaire pour une seule action ponctuelle
# (Chap 22, FAQ "dépôt privé").
#
# Usage : ./bootstrap-fleet.sh <domaine-fleet-dashboard> <email-acme>
#   ex.  ./bootstrap-fleet.sh 0-hl.com moi@example.com
#
# Idempotent : chaque étape saute si déjà faite (clone, .env, réseau,
# venv, génération du projet).
# =============================================================================

set -euo pipefail

DOMAIN="${1:?Usage: bootstrap-fleet.sh <domaine-fleet-dashboard> <email-acme>}"
ACME_EMAIL="${2:?Usage: bootstrap-fleet.sh <domaine-fleet-dashboard> <email-acme>}"

GITSKY_REPO_SSH_URL="${GITSKY_REPO_SSH_URL:-git@github.com:Nabil-Mabrouk/gitsky-v2.git}"
GITSKY_ROOT="${GITSKY_ROOT:-/opt/gitsky}"
MONOREPO_DIR="${GITSKY_ROOT}/gitsky-v2"
GENERATOR_DIR="${MONOREPO_DIR}/src/generator"
SHARED_SERVICES_SRC="${MONOREPO_DIR}/src/shared_services"
PROJECTS_DIR="${GITSKY_ROOT}/projects"
VENV_DIR="${GITSKY_ROOT}/.venv-generator"

if ! command -v docker &> /dev/null; then
    echo "✗ Docker absent — lancer harden-server.sh d'abord." >&2
    exit 1
fi

echo "1/7 Accès GitHub (clé de déploiement)..."
if ! ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo "✗ Pas d'accès SSH authentifié à GitHub." >&2
    echo "  Génère une clé dédiée, ajoute-la comme Deploy Key (lecture seule)" >&2
    echo "  sur le dépôt, puis relance ce script :" >&2
    echo "    ssh-keygen -t ed25519 -C \"$(hostname)-gitsky-deploy\" -f ~/.ssh/gitsky_deploy_key -N \"\"" >&2
    echo "    cat ~/.ssh/gitsky_deploy_key.pub" >&2
    echo "    cat >> ~/.ssh/config << 'SSHEOF'" >&2
    echo "Host github.com" >&2
    echo "  IdentityFile ~/.ssh/gitsky_deploy_key" >&2
    echo "  IdentitiesOnly yes" >&2
    echo "SSHEOF" >&2
    echo "    chmod 600 ~/.ssh/config" >&2
    exit 1
fi

echo "2/7 Clone du monorepo..."
mkdir -p "$GITSKY_ROOT" "$PROJECTS_DIR"
if [[ ! -d "$MONOREPO_DIR/.git" ]]; then
    git clone --recurse-submodules "$GITSKY_REPO_SSH_URL" "$MONOREPO_DIR"
fi
if [[ ! -e "${GITSKY_ROOT}/shared_services" ]]; then
    # Lien en dur : crontab.fleet référence /opt/gitsky/shared_services/...
    # sans variable (cron n'en expanse aucune, Chap 23).
    ln -s "$SHARED_SERVICES_SRC" "${GITSKY_ROOT}/shared_services"
fi

echo "3/7 Secrets shared_services (.env)..."
cd "$SHARED_SERVICES_SRC"
if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
fi
# sed idempotent : ne remplit que si encore vide, jamais n'écrase une valeur
# déjà posée manuellement (ex. lors d'un deuxième passage après avoir ajouté
# ANTHROPIC_API_KEY/SMTP à la main).
grep -q '^ACME_EMAIL=$' .env && sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=${ACME_EMAIL}|" .env
grep -q '^POSTGRES_ROOT_PASSWORD=$' .env && sed -i "s|^POSTGRES_ROOT_PASSWORD=.*|POSTGRES_ROOT_PASSWORD=$(openssl rand -base64 24)|" .env
grep -q '^LITELLM_MASTER_KEY=$' .env && sed -i "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-$(openssl rand -hex 24)|" .env

echo "4/7 Réseau Docker partagé..."
docker network create proxy-net 2>/dev/null || true

echo "5/7 Traefik + Postgres (services de base, toujours nécessaires)..."
docker compose up -d traefik postgres

echo "6/7 Environnement générateur (venv, versions EXACTES de requirements.txt —"
echo "    jamais codées en dur ici, pour ne jamais diverger du pin réel)..."
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --quiet -r "${GENERATOR_DIR}/requirements.txt"

echo "7/7 Génération de fleet-dashboard..."
FLEET_DIR="${PROJECTS_DIR}/fleet-dashboard"
if [[ ! -d "$FLEET_DIR" ]]; then
    cd "$MONOREPO_DIR"
    "${VENV_DIR}/bin/python" -c "
from copier import run_copy
run_copy(
    'src/generator', '${FLEET_DIR}',
    data={
        'project': {'name': 'fleet-dashboard', 'domain': '${DOMAIN}'},
        'modules': {'admin': True, 'fleet': True},
    },
    defaults=True, unsafe=True, vcs_ref='HEAD',
)
"
    cd "$FLEET_DIR"
    cp .env.local.example .env.local
    sed -i "s|^FLEET_SUBDOMAIN_SUFFIX=.*|FLEET_SUBDOMAIN_SUFFIX=.${DOMAIN}|" .env.local
    sed -i "s|^FLEET_REGISTER_TOKEN=.*|FLEET_REGISTER_TOKEN=$(openssl rand -hex 32)|" .env.local
    sed -i "s|^COLLECTOR_STATS_TOKEN=.*|COLLECTOR_STATS_TOKEN=$(openssl rand -hex 32)|" .env.local
    chmod 600 .env.local
    cat >> .env << EOF
GITSKY_GENERATOR_PATH=${GENERATOR_DIR}
GITSKY_MONOREPO_GITDIR=${MONOREPO_DIR}/.git
PROJECTS_DIR=${PROJECTS_DIR}
EOF
fi

echo ""
echo "✓ Bootstrap terminé."
echo ""
echo "Reste à faire, à la main :"
echo "  1. DNS : pointer ${DOMAIN} et api.${DOMAIN} vers l'IP de ce serveur."
echo "  2. Remplir les secrets encore vides dans shared_services/.env si besoin"
echo "     (ANTHROPIC_API_KEY, SMTP_*, MAXMIND_*) puis :"
echo "     cd ${GITSKY_ROOT}/shared_services && docker compose up -d <service>"
echo "  3. cd ${FLEET_DIR} && docker compose up -d --build"
echo "  4. ./scripts/create_admin.sh <ton-email>"
