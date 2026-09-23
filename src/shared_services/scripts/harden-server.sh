#!/usr/bin/env bash
# =============================================================================
# shared_services/scripts/harden-server.sh — Durcissement d'un Ubuntu 24.04 vierge.
# (Chap 22, jusqu'à "Installation de Docker" — la partie SSH par clé reste
# manuelle, voir plus bas.)
#
# Précondition NON automatisée, volontairement : un accès SSH par clé déjà
# fonctionnel. Générer/déposer la clé et désactiver l'auth par mot de passe
# reste une procédure manuelle (chapitre 22, "Sécurisation SSH par Clé
# Publique") — se tromper à cette étape peut verrouiller l'opérateur hors
# d'un VPS tout juste loué, sans filet. Un script qui l'automatiserait
# économiserait 2 minutes au prix d'un risque qui n'en vaut pas la peine.
#
# Idempotent : chaque étape peut être rejouée sans casser un état déjà en
# place (apt/ufw/fail2ban/docker gèrent tous nativement le "déjà fait").
#
# Usage : ./harden-server.sh
#   (aucun argument — rien ici n'est propre à un projet ou un domaine)
# =============================================================================

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "✗ Ce script doit tourner en root (ou via sudo)." >&2
    exit 1
fi

echo "1/5 Mise à jour du système..."
apt update -y
apt upgrade -y
echo "  ⚠ Un redémarrage est recommandé si un nouveau noyau a été installé"
echo "    (apt l'indique ci-dessus) — 'reboot', puis relancer ce script."

echo "2/5 Paquets de base..."
apt install -y curl git unzip ufw fail2ban htop

echo "3/5 Pare-feu UFW..."
# --force : ne pas bloquer sur la confirmation interactive habituelle de
# `ufw enable` — ce script tourne déjà en connaissance de cause (Chap 22).
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "4/5 fail2ban..."
if [[ ! -f /etc/fail2ban/jail.local ]]; then
    cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
EOF
fi
systemctl enable fail2ban
systemctl restart fail2ban

echo "5/5 Docker (dépôt officiel, pas apt install docker.io — Chap 22)..."
if ! command -v docker &> /dev/null; then
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt update -y
    apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable docker
systemctl start docker

echo ""
echo "✓ Serveur durci."
docker --version
docker compose version
ufw status | head -1
fail2ban-client status sshd | head -1
echo ""
echo "Prochaine étape : ./bootstrap-fleet.sh <domaine-fleet-dashboard> <email-acme>"
