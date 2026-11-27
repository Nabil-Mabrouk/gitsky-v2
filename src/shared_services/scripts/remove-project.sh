#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/remove-project.sh — Supprime DÉFINITIVEMENT un projet
# du serveur (2026-11-27, retrait de politique-ia, cryptazy, cryptokilla).
#
# À lancer APRÈS l'avoir archivé depuis sa fiche dans le fleet dashboard
# (statut « archivé », la flotte cesse de le surveiller). Dans l'ordre :
#   1. demande de retaper le nom du projet (aucune action sans cela) ;
#   2. révoque sa clé LLM dans le proxy, s'il en a une (llm-proxy-keys.sh) ;
#   3. docker compose down -v --rmi local : conteneurs, réseaux, VOLUMES
#      (base de données et fichiers) et images construites du projet ;
#   4. supprime sa clé de déploiement SSH et son bloc dans ~/.ssh/config ;
#   5. supprime le dossier du projet.
# Ne touche ni au dépôt GitHub, ni au DNS, ni à Umami : rappels affichés à la fin.
# Aucune sauvegarde n'est faite ici : les dumps nocturnes déjà présents dans
# /backups/postgres disparaissent d'eux-mêmes avec la rotation.
#
# Usage : remove-project.sh <nom-projet>
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECTS_DIR="${PROJECTS_DIR:-/opt/gitsky/projects}"
SSH_DIR="${SSH_DIR:-${HOME}/.ssh}"

PROJECT="${1:-}"
if [[ $# -ne 1 || ! "$PROJECT" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "Usage : $0 <nom-projet>   (minuscules, chiffres, tirets)" >&2
    exit 2
fi
if [[ "$PROJECT" == "fleet-dashboard" ]]; then
    echo "✗ refusé : fleet-dashboard est le tableau de bord de la flotte elle-même." >&2
    exit 1
fi

DIR="${PROJECTS_DIR}/${PROJECT}"
[[ -d "$DIR" ]] || { echo "✗ projet introuvable : ${DIR}" >&2; exit 1; }

echo "Suppression DÉFINITIVE de ${PROJECT} : conteneurs, base de données, fichiers,"
echo "images, clé de déploiement et dossier ${DIR}. Aucune sauvegarde n'est faite."
read -rp "Retaper le nom du projet pour confirmer : " CONFIRM
if [[ "$CONFIRM" != "$PROJECT" ]]; then
    echo "✗ confirmation différente du nom du projet : rien n'a été supprimé." >&2
    exit 1
fi

# 2. Clé LLM (avant de supprimer le dossier : le jeton est dans son .env.local).
if grep -qE '^LLM_PROXY_TOKEN=.+' "${DIR}/.env.local" 2>/dev/null; then
    "${SCRIPT_DIR}/llm-proxy-keys.sh" delete-key "$PROJECT"
else
    echo "• pas de clé LLM à révoquer."
fi

# 3. Conteneurs, volumes, images.
(cd "$DIR" && docker compose down -v --rmi local)
echo "✓ conteneurs, volumes et images supprimés."

# 4. Clé de déploiement (créée par setup-deploy-key.sh).
rm -f "${SSH_DIR}/${PROJECT}_deploy_key" "${SSH_DIR}/${PROJECT}_deploy_key.pub"
if [[ -f "${SSH_DIR}/config" ]] && grep -q "^Host github.com-${PROJECT}$" "${SSH_DIR}/config"; then
    # Le bloc fait 4 lignes (Host + 3 réglages) ; sed -i garde les droits 600.
    sed -i "/^Host github.com-${PROJECT}$/,+3d" "${SSH_DIR}/config"
fi
echo "✓ clé de déploiement retirée."

# 5. Dossier du projet.
rm -rf "$DIR"
echo "✓ dossier ${DIR} supprimé."

echo
echo "Reste à faire hors du serveur, si ce n'est pas déjà fait :"
echo "  - fleet dashboard : le projet doit être « archivé » (fiche projet) ;"
echo "  - IONOS : supprimer les enregistrements DNS du domaine et de api.<domaine> ;"
echo "  - GitHub : archiver le dépôt et supprimer son webhook vers 0-hitl.com ;"
echo "  - Umami : supprimer le site du projet s'il en avait un."
