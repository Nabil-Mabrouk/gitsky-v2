# Configuration du Serveur de Production

## Ubuntu Server 24.04 — Sécurisation, Docker et Accès SSH

## Prérequis et Contexte

Ce chapitre couvre la mise en place complète d'un serveur Ubuntu 24.04 fraîchement
installé, depuis la première connexion jusqu'au déploiement de l'infrastructure
Docker. Les opérations sont à effectuer dans l'ordre indiqué.

**Ce dont tu as besoin avant de commencer :**

- Un serveur Ubuntu 24.04 avec une IP publique
- PuTTY et PuTTYgen installés sur ton poste Windows
- Un accès root initial par mot de passe (fourni par ton hébergeur)


## Première Connexion avec PuTTY

### nstaller PuTTY

Télécharge la suite complète depuis le site officiel :
`https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html`

Installe le package **MSI 64-bit** — il inclut PuTTY, PuTTYgen et Pageant.

### Configurer et sauvegarder une session PuTTY

Ouvre PuTTY et configure ta session avant la première connexion — tu n'auras
plus à ressaisir ces paramètres ensuite.

```text
PuTTY Configuration
|
+-- Session
|     Host Name : 217.76.61.192       (l'IP de ton serveur)
|     Port      : 22
|     Connection type : SSH
|     Saved Sessions : "mon-serveur-prod"   <- donne un nom
|
+-- Connection
|   +-- Data
|         Auto-login username : root
|   +-- SSH
|       +-- Auth
|           +-- Credentials
|                 Private key file : (laisser vide pour l'instant)
|
+-- Session
      -> bouton [Save]
```

Double-clique sur le nom de la session sauvegardée pour te connecter.
PuTTY te demande le mot de passe root fourni par ton hébergeur.


## Sécurisation SSH par Clé Publique

L'objectif est de remplacer l'authentification par mot de passe — vulnérable
au bruteforce — par une authentification par clé cryptographique.

> **Règle absolue :** ne désactiver le mot de passe SSH qu'après avoir
> vérifié que la connexion par clé fonctionne. Ne jamais fermer la session
> courante avant ce test.

### Générer une Paire de Clés avec PuTTYgen

Ouvre **PuTTYgen** (installé avec PuTTY).

```
+--------------------------------------------------+
|                   PuTTYgen                       |
|                                                  |
|  1. Type of key to generate :                   |
|     ( ) RSA  ( ) DSA  ( ) ECDSA  (o) EdDSA       |
|     ( ) SSH-1 (RSA)                              |
|     Curve : [Ed25519]  <- selectionner           |
|                                                  |
|  2. Cliquer [Generate]                           |
|     Bouger la souris dans la zone vide           |
|                                                  |
|  3. Key comment : monnom@monpc                   |
|                                                  |
|  4. Key passphrase    : [mot de passe fort]      |
|     Confirm passphrase: [meme mot de passe]      |
|                                                  |
|  5. [Save private key] -> serveur_prod.ppk       |
|                                                  |
|  NE PAS FERMER PUTTY GEN                         |
+--------------------------------------------------+
```

**ED25519** est l'algorithme recommandé en 2024 — plus court, plus rapide et
plus sûr que RSA 2048.

> Ce mockup correspond à PuTTYgen 0.75 et versions plus récentes — EdDSA
> (avec un sélecteur de courbe séparé) a remplacé un ancien menu "Key type"
> plus simple dans les versions antérieures à 2020. Si EdDSA n'apparaît pas
> du tout dans ta liste, vérifie ta version via **Help → About** et
> réinstalle le paquet MSI le plus récent. A défaut, ECDSA (courbe
> nistp256) ou RSA 4096 bits sont des alternatives valables pour la suite
> de la procédure.

La **passphrase** protège ta clé privée sur ton poste. Si quelqu'un vole ton
fichier `.ppk`, il ne peut rien faire sans elle.

Sauvegarde le fichier `.ppk` dans `C:\Users\toi\.ssh\serveur_prod.ppk`.
Fais immédiatement une copie de sauvegarde sur un support externe ou dans
un gestionnaire de mots de passe (Bitwarden, 1Password).

### Déposer la Clé Publique sur le Serveur

Dans ta session PuTTY ouverte (connecté par mot de passe), exécute :

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
```

Dans PuTTYgen, copie le contenu de la zone **"Public key for pasting into
OpenSSH authorized_keys"**. C'est la grande zone de texte en haut de
PuTTYgen. Elle ressemble à :

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBx... monnom@monpc
```

Colle cette ligne dans nano, puis :

- Sauvegarder : `Ctrl+O` puis `Entree`
- Quitter : `Ctrl+X`

```bash
chmod 600 ~/.ssh/authorized_keys
```

### Configurer PuTTY pour Utiliser la Clé

Dans PuTTY, charge ta session sauvegardée et modifie-la :

```
PuTTY Configuration
|
+-- Connection -> SSH -> Auth -> Credentials
|     Private key file for authentication :
|     [Browse...] -> selectionner serveur_prod.ppk
|
+-- Session
      -> [Save]   <- sauvegarder les modifications
```

### Tester la Connexion par Clé

**Sans fermer ta session actuelle**, ouvre une nouvelle fenêtre PuTTY et
double-clique sur ta session sauvegardée.

PuTTY doit te demander la **passphrase de ta clé** (pas le mot de passe
du serveur). Entre-la — tu es connecté.

Si la connexion échoue, consulte la section FAQ en fin de chapitre avant
de continuer.

### Désactiver l'Authentification par Mot de Passe

Une fois la connexion par clé vérifiée et fonctionnelle :

```bash
nano /etc/ssh/sshd_config
```

Localise et modifie ces lignes (utilise `Ctrl+W` pour chercher dans nano) :

```bash
PasswordAuthentication no
PermitRootLogin prohibit-password
```

`prohibit-password` autorise root à se connecter uniquement par clé —
le mot de passe root devient inutilisable à distance, ce qui est plus
sûr que de bloquer root complètement (tu pourrais avoir besoin d'accès
en cas de problème avec un utilisateur secondaire).

```bash
systemctl restart ssh
```

Teste une dernière fois depuis une nouvelle fenêtre PuTTY. Les bots
que fail2ban surveille ne peuvent désormais plus rien faire — il n'y a
plus de mot de passe à bruteforcer.


## Mise à Jour du Système

```bash
apt update && apt upgrade -y
reboot
```

Le redémarrage applique les éventuels nouveaux noyaux installés lors de
la mise à jour. Reconnecte-toi après le redémarrage.

## Installation des Paquets de Base

```bash
apt install -y \
  curl \
  git \
  unzip \
  ufw \
  fail2ban \
  htop
```

| Paquet | Rôle |
|---|---|
| `curl` | Téléchargements HTTP depuis le terminal |
| `git` | Cloner les dépôts de tes projets |
| `unzip` | Décompression d'archives |
| `ufw` | Pare-feu simplifié |
| `fail2ban` | Protection contre le bruteforce |
| `htop` | Monitoring CPU/mémoire interactif |

## Configuration du Pare-feu UFW

```bash
ufw default deny incoming    # Bloquer tout le trafic entrant par défaut
ufw default allow outgoing   # Autoriser tout le trafic sortant

ufw allow ssh                # Port 22 — NE PAS OUBLIER
ufw allow 80/tcp             # HTTP  (Traefik)
ufw allow 443/tcp            # HTTPS (Traefik)

ufw enable
```

Vérifie l'état :

```bash
ufw status verbose
```

```text
+-------------------------------------------+
|           UFW STATUS                      |
|                                           |
|  To          Action    From               |
|  --          ------    ----               |
|  22/tcp      ALLOW     Anywhere           |
|  80/tcp      ALLOW     Anywhere           |
|  443/tcp     ALLOW     Anywhere           |
|                                           |
|  Ports NON ouverts (restes internes) :    |
|  5432 (PostgreSQL)                        |
|  6379 (Redis)                             |
|  8080 (Dashboard Traefik)                 |
+-------------------------------------------+
```

> **Ne jamais ouvrir les ports 5432 et 6379.** PostgreSQL et Redis sont
> accessibles uniquement via les réseaux internes Docker — ils ne doivent
> jamais être joignables depuis l'extérieur.

## Configuration de Fail2ban

Fail2ban surveille les logs du serveur et banne automatiquement les IPs
qui échouent trop souvent à s'authentifier.

```bash
nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
```

```bash
systemctl enable fail2ban
systemctl restart fail2ban
```

Vérifie que la jail SSH est active :

```bash
fail2ban-client status sshd
```

Tu verras les IPs déjà bannies — les bots scannent en permanence les
serveurs exposés sur internet. C'est normal d'en voir plusieurs dès les
premières minutes.

## Installation de Docker

Ne pas utiliser `apt install docker.io` — c'est une version ancienne
maintenue par Ubuntu. Utiliser le dépôt officiel Docker :

```bash
# Clé GPG officielle Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Ajout du dépôt officiel
echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Installation
apt update
apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

Vérifie l'installation :

```bash
docker --version
docker compose version
```

Active Docker au démarrage :

```bash
systemctl enable docker
systemctl start docker
```

## Structure des Répertoires

```bash
mkdir -p /opt/traefik/config
mkdir -p /backups
```

```text
+------------------------------------------+
|  /opt/                                   |
|  +-- traefik/                            |
|  |   +-- docker-compose.yml             |
|  |   +-- config/                        |
|  |       +-- middlewares.yml            |
|  |                                      |
|  +-- projet-a/    <- git clone          |
|  +-- projet-b/    <- git clone          |
|                                         |
|  /backups/                              |
|  +-- projet-a/                          |
|  +-- projet-b/                          |
+------------------------------------------+
```

## Déploiement du Traefik Partagé

Crée le fichier de configuration :

```bash
nano /opt/traefik/docker-compose.yml
```

```yaml
services:
  traefik:
    image: traefik:v3.0.4
    container_name: traefik_shared
    restart: always
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--providers.docker.network=proxy-net"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      # Redirection HTTP -> HTTPS globale pour tous les projets
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
      - "--entrypoints.web.http.redirections.entrypoint.permanent=true"
      # Let's Encrypt
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
      - "--providers.file.directory=/etc/traefik/config"
      - "--providers.file.watch=true"
      - "--accesslog=true"
      - "--log.level=WARN"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik_certs:/letsencrypt
      - ./config:/etc/traefik/config:ro
    networks:
      - proxy-net
    security_opt:
      - no-new-privileges:true

volumes:
  traefik_certs:

networks:
  proxy-net:
    name: proxy-net
    driver: bridge
```

Crée le fichier `.env` de Traefik :

```bash
nano /opt/traefik/.env
```

```bash
ACME_EMAIL=ton@email.com
```

Crée les middlewares partagés :

```bash
nano /opt/traefik/config/middlewares.yml
```

```yaml
http:
  middlewares:
    security-headers:
      headers:
        frameDeny: true
        contentTypeNosniff: true
        browserXssFilter: true
        referrerPolicy: "strict-origin-when-cross-origin"
        forceSTSHeader: true
        stsSeconds: 31536000
        stsIncludeSubdomains: true

    rate-limit:
      rateLimit:
        average: 100
        burst: 50
```

Lance Traefik :

```bash
cd /opt/traefik
docker compose up -d
docker compose logs -f    # Verifier qu'il demarre sans erreur
```

## Récapitulatif de l'État du Serveur

Une fois toutes les étapes effectuées, voici ce que tu dois avoir :

```text
+------------------------------------------------+
|           ETAT DU SERVEUR                      |
+------------------------+-----------------------+
| Composant              | Etat attendu          |
+------------------------+-----------------------+
| SSH par cle            | Actif                 |
| Mot de passe SSH       | Desactive             |
| UFW                    | Actif (22,80,443)     |
| Fail2ban               | Actif, jail sshd OK   |
| Docker Engine          | Actif                 |
| Docker Compose         | Disponible            |
| Traefik shared         | Conteneur running     |
| proxy-net              | Reseau cree           |
+------------------------+-----------------------+
```

Commandes de vérification globale :

```bash
ufw status              # Pare-feu
fail2ban-client status  # Jails actives
docker ps               # Conteneurs running
docker network ls       # Reseaux Docker
```

## FAQ

---

**Q : PuTTY me demande toujours le mot de passe après avoir configuré la clé.**

La clé n'est pas chargée dans la session. Dans PuTTY, charge ta session
sauvegardée, va dans **Connection → SSH → Auth → Credentials**, clique sur
**Browse** et sélectionne ton fichier `.ppk`. Puis remonte dans **Session**
et clique sur **Save** avant de te connecter.

---

**Q : PuTTY affiche "Access denied" en boucle.**

Deux causes possibles :

- Le mot de passe SSH a déjà été désactivé sur le serveur et PuTTY n'utilise
  pas encore la clé. Configurer la clé dans PuTTY comme décrit ci-dessus.
- La clé publique n'a pas été correctement copiée dans `authorized_keys`.
  Si tu as encore accès au serveur via la console de ton hébergeur (KVM,
  VNC, console web), vérifie le contenu du fichier :
  `cat ~/.ssh/authorized_keys`

---

**Q : J'ai perdu ma clé `.ppk`. Je n'arrive plus à me connecter.**

La plupart des hébergeurs proposent un accès console d'urgence (KVM, VNC,
ou console web dans le panel) qui ne passe pas par SSH. Connecte-toi via
cette console, puis :

```bash
# Remettre temporairement l'auth par mot de passe
nano /etc/ssh/sshd_config
# Passer PasswordAuthentication a yes
systemctl restart ssh
```

Génère une nouvelle paire de clés, redépose la clé publique, puis
redésactive le mot de passe.

---

**Q : Fail2ban a banni ma propre IP.**

```bash
fail2ban-client set sshd unbanip TON_IP
```

Pour éviter que ça se reproduise, ajoute ton IP dans la whitelist dans
`/etc/fail2ban/jail.local` :

```ini
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1 TON_IP_FIXE
```

Cela n'est utile que si ton FAI te fournit une IP fixe.

---

**Q : Comment connaître ma propre IP publique pour la whitelist ?**

Attention : contrairement aux autres commandes de cette FAQ, celle-ci
s'exécute **sur ta machine locale, pas dans la session SSH** —
`curl ifconfig.me` lancé depuis le serveur renvoie l'IP du serveur
lui-même, pas la tienne.

```bash
# Sur TON PC (PowerShell), pas dans la session SSH :
curl ifconfig.me
```

Plus fiable : demande directement au serveur quelle IP source a servi à ta
session en cours — c'est exactement celle que fail2ban voit passer.

```bash
# Sur le serveur, dans ta session SSH active :
who
# ou, pour l'historique récent :
last -a | head -5
```

Si ta machine dispose à la fois d'IPv4 et d'IPv6, les deux méthodes peuvent
renvoyer des adresses différentes selon la pile réseau empruntée par
chaque connexion. En cas de doute, fais confiance à `who`/`last -a`, qui
reflète la connexion SSH réelle plutôt qu'une requête HTTP séparée.

---

**Q : Traefik ne génère pas le certificat Let's Encrypt.**

Trois causes fréquentes :

- Le DNS du domaine ne pointe pas encore vers l'IP du serveur. Let's Encrypt
  ne peut pas valider un domaine qui n'est pas résolu. Vérifie avec :
  `nslookup mondomaine.com`
- Le port 80 est bloqué par UFW. Let's Encrypt utilise le challenge HTTP
  sur le port 80 pour valider le domaine. Vérifier : `ufw status`
- Le fichier `acme.json` a des permissions incorrectes. Traefik le crée
  lui-même dans le volume — ne pas le toucher manuellement.

---

**Q : Comment voir les domaines et certificats gérés par Traefik ?**

```bash
# Inspecter les logs Traefik
docker logs traefik_shared 2>&1 | grep -i "acme\|certificate\|error"

# Lister les routes actives
docker exec traefik_shared traefik version

# Inspecter le fichier acme.json (certificats stockes)
docker exec traefik_shared cat /letsencrypt/acme.json | python3 -m json.tool
```

---

**Q : Comment ajouter un nouveau projet sur le serveur ?**

```bash
cd /opt
git clone https://github.com/toi/mon-projet.git
cd mon-projet
cp .env.example .env.prod
nano .env.prod    # Remplir les secrets
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Traefik détecte automatiquement les nouveaux conteneurs et configure le
routing — aucune intervention sur Traefik lui-même.

Si le dépôt est **privé**, le `git clone` en HTTPS ci-dessus demande un
mot de passe que GitHub refuse — voir l'entrée suivante.

---

**Q : Le dépôt est privé — `git clone` me demande un mot de passe. Comment faire ?**

GitHub n'accepte plus l'authentification par mot de passe en HTTPS depuis
2021. Deux options : un token d'accès personnel, ou une clé de déploiement
SSH. Pour un serveur qui va cloner puis régulièrement `git pull` /
`copier update` (Chap 25 §3.4), la clé de déploiement est préférable —
scopée à un seul dépôt, en lecture seule, sans identifiant stocké sur le
serveur.

Génère une paire de clés dédiée sur le serveur :

```bash
ssh-keygen -t ed25519 -C "nom-serveur-deploy" -f ~/.ssh/gitsky_deploy_key -N ""
cat ~/.ssh/gitsky_deploy_key.pub
```

Ajoute la clé publique affichée dans **GitHub → ton dépôt → Settings →
Deploy keys → Add deploy key**, sans cocher "Allow write access" — le
serveur n'a besoin que de lire.

Indique à SSH d'utiliser cette clé pour GitHub :

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/gitsky_deploy_key
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

Teste l'authentification **avant** de cloner :

```bash
ssh -T git@github.com
# "Hi <compte>/<depot> ! You've successfully authenticated..."
```

Clone ensuite via l'URL SSH (`git@github.com:...`), pas l'URL HTTPS :

```bash
git clone git@github.com:toi/mon-depot-prive.git
```

> Erreur fréquente : `no such identity: /root/.ssh/gitsky_deploy_key: No
> such file or directory` — la clé n'a pas été générée avant que
> `~/.ssh/config` ne la référence. Vérifier avec `ls -la ~/.ssh` et
> relancer `ssh-keygen` si le fichier est absent.

---

**Q : Un conteneur redémarre en boucle. Comment diagnostiquer ?**

```bash
# Voir l'état de tous les conteneurs
docker ps -a

# Logs du conteneur en erreur
docker logs NOM_DU_CONTENEUR --tail=50

# Suivre les logs en temps réel
docker logs NOM_DU_CONTENEUR -f

# Inspecter la configuration du conteneur
docker inspect NOM_DU_CONTENEUR
```

---

**Q : Le serveur est lent ou sature. Comment identifier la cause ?**

```bash
# Vue globale CPU/RAM/swap en temps reel
htop

# Consommation par conteneur Docker
docker stats

# Espace disque
df -h

# Les processus qui consomment le plus d'I/O disque
iotop -o
```

---

**Q : Comment mettre à jour Docker ?**

```bash
apt update
apt install --only-upgrade docker-ce docker-ce-cli containerd.io
```

Docker est rétrocompatible — la mise à jour du moteur n'affecte pas les
conteneurs en cours d'exécution.

---

**Q : Comment sauvegarder les certificats Traefik ?**

Le volume `traefik_certs` contient le fichier `acme.json` avec tous les
certificats. L'inclure dans la stratégie de sauvegarde :

```bash
docker run --rm \
  -v traefik_certs:/data \
  -v /backups:/backup \
  alpine tar czf /backup/traefik_certs_$(date +%Y%m%d).tar.gz -C /data .
```

En pratique, la perte des certificats n'est pas catastrophique — Traefik
les renouvelle automatiquement via Let's Encrypt. Le seul impact est
quelques minutes sans HTTPS lors du renouvellement.

---

## Bootstrap des Services Partagés pour une Flotte

Sur ce serveur Ubuntu durci, l'installation de la flotte GitSky consiste à
déployer une fois pour toutes les services partagés décrits au Chap 18,
puis à laisser le générateur (Chap 17) déployer les projets individuellement.

### Le Script `bootstrap-fleet.sh`

Un unique script d'orchestration installe l'ensemble des services partagés :

```bash
# scripts/bootstrap-fleet.sh
#!/usr/bin/env bash
set -euo pipefail

echo "1/6 Création des réseaux Docker partagés..."
docker network create proxy-net || true
docker network create shared-services-net || true

echo "2/6 Démarrage de Traefik (wildcard SSL)..."
(cd shared-services/traefik && docker compose up -d)

echo "3/6 Démarrage de PostgreSQL partagé..."
(cd shared-services/postgres && docker compose up -d)

echo "4/6 Démarrage du landing-collector, GeoIP, SMTP relay..."
(cd shared-services/landing-collector && docker compose up -d)
(cd shared-services/geoip && docker compose up -d)
(cd shared-services/smtp-relay && docker compose up -d)

echo "5/6 Démarrage du LLM proxy..."
(cd shared-services/llm-proxy && docker compose up -d)

echo "6/6 Démarrage du fleet dashboard..."
(cd shared-services/fleet-dashboard && docker compose up -d)

echo "Flotte prête. Les projets peuvent être générés."
```

Ce script est idempotent — il peut être ré-exécuté pour redémarrer les
services après un reboot.

### Répertoire de Travail sur le Serveur

L'organisation recommandée du système de fichiers :

```text
/opt/mystudio/
├── shared-services/         # Services partagés du VPS (versionné)
│   ├── traefik/
│   ├── postgres/
│   ├── llm-proxy/
│   └── …
├── projects/                # Un dossier par projet généré
│   ├── pain-scraper/
│   ├── code-reviewer-pro/
│   └── …
├── configs/                 # Fichiers config.yaml (repo startup-factory-configs)
│   └── projects/
└── backups/                 # Voir Chap 23
```

Chaque dossier de projet est un clone du template GitSky avec les
substitutions du générateur appliquées. Les projets **ne partagent pas
de code** entre eux — seuls les services externes sont mutualisés.

### fail2ban et Traefik

L'analyse des `SecurityEvent` de tous les projets (Chap 14) alimente une
règle fail2ban qui pousse les IPs agressives dans une allowlist négative
Traefik, transformant la détection applicative par projet en blocage
réseau mutualisé — sans avoir à configurer fail2ban par projet.

### Isolation par Projet : Ce qui est Vraiment Isolé

Trois niveaux d'isolation stricts :

| Niveau | Isolation | Partage |
|---|---|---|
| Conteneurs applicatifs | 1 backend + 1 frontend par projet | Le réseau `proxy-net` (Traefik uniquement) |
| Base de données | 1 DB PostgreSQL par projet | Le processus PostgreSQL |
| Secrets | 1 fichier `.env` par projet | Aucun |

Un attaquant qui compromet un projet ne peut atteindre ni les autres
projets ni les services partagés. Le seul chemin latéral serait via
Traefik lui-même — d'où l'importance de le tenir à jour.

---

*Le serveur est prêt à porter la flotte. Le dernier chapitre couvre la maintenance quotidienne et hebdomadaire nécessaire pour la garder en bonne santé sur la durée.*