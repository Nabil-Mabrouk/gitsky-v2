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

echo "1/9 Accès GitHub (clé de déploiement)..."
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

echo "2/9 Clone du monorepo..."
mkdir -p "$GITSKY_ROOT" "$PROJECTS_DIR"
if [[ ! -d "$MONOREPO_DIR/.git" ]]; then
    git clone --recurse-submodules "$GITSKY_REPO_SSH_URL" "$MONOREPO_DIR"
fi
if [[ ! -e "${GITSKY_ROOT}/shared_services" ]]; then
    # Lien en dur : crontab.fleet référence /opt/gitsky/shared_services/...
    # sans variable (cron n'en expanse aucune, Chap 23).
    ln -s "$SHARED_SERVICES_SRC" "${GITSKY_ROOT}/shared_services"
fi

echo "3/9 Secrets shared_services (.env)..."
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

echo "4/9 Réseau Docker partagé..."
docker network create proxy-net 2>/dev/null || true

echo "5/9 Traefik + Postgres (services de base, toujours nécessaires)..."
docker compose up -d traefik postgres

echo "6/9 Environnement générateur (venv, versions EXACTES de requirements.txt —"
echo "    jamais codées en dur ici, pour ne jamais diverger du pin réel)..."
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --quiet -r "${GENERATOR_DIR}/requirements.txt"

echo "7/9 Génération de fleet-dashboard..."
FLEET_DIR="${PROJECTS_DIR}/fleet-dashboard"
FLEET_REGISTER_TOKEN="$(openssl rand -hex 32)"
FRESH_FLEET=0
if [[ ! -d "$FLEET_DIR" ]]; then
    FRESH_FLEET=1
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
    sed -i "s|^FLEET_REGISTER_TOKEN=.*|FLEET_REGISTER_TOKEN=${FLEET_REGISTER_TOKEN}|" .env.local
    sed -i "s|^COLLECTOR_STATS_TOKEN=.*|COLLECTOR_STATS_TOKEN=$(openssl rand -hex 32)|" .env.local
    chmod 600 .env.local
    cat >> .env << EOF
GITSKY_GENERATOR_PATH=${GENERATOR_DIR}
GITSKY_MONOREPO_GITDIR=${MONOREPO_DIR}/.git
PROJECTS_DIR=${PROJECTS_DIR}
EOF
else
    # Script rejoué sur un fleet-dashboard déjà généré : reprend le jeton
    # déjà posé (Étape 9/cron en a besoin), jamais un nouveau — un second
    # jeton désynchroniserait fleet-health.sh/deploy-on-push.sh du cron déjà
    # installé lors d'un premier passage.
    FLEET_REGISTER_TOKEN="$(grep '^FLEET_REGISTER_TOKEN=' "${FLEET_DIR}/.env.local" | cut -d= -f2-)"
fi

echo "8/9 Personnalisation fleet-dashboard (copier/git — Chap 27)..."
# Bug de prod réel (ai-qube, 2026-09-23) : ces trois personnalisations sont
# TOUJOURS nécessaires pour tout fleet-dashboard (le wizard échoue sinon en
# ModuleNotFoundError/git introuvable dès la première utilisation) — jamais
# optionnelles, donc automatisées ici plutôt que "à faire à la main" comme
# documenté au Chap 27 pour un projet ordinaire.
if ! grep -q "^copier==" "${FLEET_DIR}/requirements.txt" 2>/dev/null; then
    {
        echo ""
        echo "# Chap 27 : uniquement pour module_fleet (génération de projets via le wizard)"
        grep "^copier" "${GENERATOR_DIR}/requirements.txt"
    } >> "${FLEET_DIR}/requirements.txt"
fi
if ! grep -q "safe.directory" "${FLEET_DIR}/Dockerfile" 2>/dev/null; then
    "${VENV_DIR}/bin/python" -c "
from pathlib import Path
dockerfile = Path('${FLEET_DIR}/Dockerfile')
content = dockerfile.read_text()
git_install = (
    '# Chap 27 : git requis par les taches de generation (copier),\n'
    '# absent de python:3.12-slim - specifique a module_fleet.\n'
    'RUN apt-get update && apt-get install -y --no-install-recommends git '
    '&& rm -rf /var/lib/apt/lists/*\n\n'
)
content = content.replace('RUN mkdir -p /data', git_install + 'RUN mkdir -p /data')
safe_dir = (
    '\n# Chap 27 : depots montes depuis l host appartiennent a root, copier tourne\n'
    '# comme appuser - sans ca, git refuse (dubious ownership), _commit ne se\n'
    '# resout jamais, aucune erreur visible.\n'
    'RUN git config --global --add safe.directory \"*\"\n'
)
content = content.replace('USER appuser\n', 'USER appuser\n' + safe_dir)
dockerfile.write_text(content)
"
fi

echo "9/9 Démarrage fleet-dashboard, ownership, cron..."
cd "$FLEET_DIR"
docker compose up -d --build

# UID réel de appuser DANS l'image construite — jamais supposé (system user,
# assigné par l'OS, pas garanti identique d'une base image à l'autre). Bug
# de prod réel (ai-qube, 2026-09-23) : sans ce chown, toute génération de
# projet via le wizard échouait en PermissionError (le conteneur tourne en
# appuser, jamais root — Chap 21 — mais PROJECTS_DIR appartenait à root).
APPUSER_UID="$(docker exec fleet-dashboard_backend id -u appuser)"
chown -R "${APPUSER_UID}:${APPUSER_UID}" "$PROJECTS_DIR"

# crontab.fleet : sans lui, un projet créé via le wizard ne démarre JAMAIS
# tout seul — le webhook GitHub ne fait que journaliser deploy_triggered,
# c'est deploy-on-push.sh (ce cron) qui exécute le vrai redeploy (Chap 26).
# Bug de prod réel (ai-qube, 2026-09-23) : jamais installé par ce script,
# trouvé en créant le tout premier projet via le wizard.
EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
if ! grep -q "deploy-on-push.sh" <<< "$EXISTING_CRON"; then
    sed \
        -e "s|^FLEET_URL=.*|FLEET_URL=https://api.${DOMAIN}|" \
        -e "s|^FLEET_REGISTER_TOKEN=.*|FLEET_REGISTER_TOKEN=${FLEET_REGISTER_TOKEN}|" \
        "${SHARED_SERVICES_SRC}/crontab.fleet" | crontab -
fi

echo ""
echo "✓ Bootstrap terminé — fleet-dashboard tourne sur https://${DOMAIN} une fois le DNS propagé."
echo ""
echo "Reste à faire, à la main :"
echo "  1. DNS : pointer ${DOMAIN} et api.${DOMAIN} vers l'IP de ce serveur"
echo "     (Traefik n'obtiendra un vrai certificat qu'une fois le DNS propagé —"
echo "     un 'docker restart shared_services-traefik-1' peut être nécessaire"
echo "     pour forcer une nouvelle tentative si le DNS a été posé après coup)."
echo "  2. Remplir les secrets encore vides dans shared_services/.env si besoin"
echo "     (ANTHROPIC_API_KEY, SMTP_*, MAXMIND_*) puis :"
echo "     cd ${GITSKY_ROOT}/shared_services && docker compose up -d <service>"
echo "  3. cd ${FLEET_DIR} && ./scripts/create_admin.sh <ton-email>"
echo "  4. Pour créer un projet PRIVÉ via le wizard : une clé de déploiement"
echo "     SSH dédiée est nécessaire pour que le redeploy continu fonctionne"
echo "     (le premier push, lui, marche déjà via FLEET_GITHUB_TOKEN) —"
echo "     voir setup-deploy-key.sh."
if [[ $FRESH_FLEET -eq 0 ]]; then
    echo "(fleet-dashboard existait déjà — étapes 7/8 rejouées sans effet, jeton cron repris tel quel.)"
fi
