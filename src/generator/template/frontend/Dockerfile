# Dockerfile de PRODUCTION du frontend (Chap 21).
#
# Trois stages : deps (npm ci) -> build (npm run build) -> production (le seul
# dossier dist, servi par `serve`). Les node_modules et le toolchain Vite ne
# franchissent jamais le dernier stage.
#
# Ne pas éditer à la main : modifier le template du générateur.

# ── Stage 1 : dépendances ────────────────────────────────────────────────────
# ÉCART AU LIVRE : le Chap 23 (update_images.sh) tire `node:20-alpine`. Node 20
# est en fin de vie depuis le 2026-04-30 — plus aucun correctif de sécurité, ce
# qui contredit le chapitre même qui organise le patching. Node 24 est la LTS
# active (fin de vie 2028-04-30).
FROM node:24-alpine AS deps

WORKDIR /app

# npm ci (et non npm install) : installe EXACTEMENT le lockfile. C'est ce qui
# rend le build reproductible et donne une cible stable au `npm audit` du Chap 23.
COPY package.json package-lock.json ./
RUN npm ci

# ── Stage 2 : build ──────────────────────────────────────────────────────────
FROM node:24-alpine AS build

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Vite INLINE les variables VITE_* dans le bundle au moment du build : l'URL de
# l'API ne peut donc pas être injectée au runtime, elle doit arriver ici.
# (Une variable déjà présente dans l'environnement est prioritaire sur les
# fichiers .env — c'est ce qui permet à cet ARG de gagner.)
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

# Sans valeur, Vite inlinerait une chaîne vide et livrerait un bundle qui
# n'appelle aucune API — panne silencieuse. On échoue au build, pas en prod.
RUN test -n "$VITE_API_URL" \
    || (echo "ERREUR: build-arg VITE_API_URL requis (inliné par Vite)." && exit 1)

RUN npm run build

# ── Stage 3 : production ─────────────────────────────────────────────────────
FROM node:24-alpine AS production

# serve : serveur statique léger (Chap 21).
RUN npm install -g serve@14

WORKDIR /app

# L'image node fournit déjà un utilisateur `node` non-root (règle du Chap 21).
COPY --from=build --chown=node:node /app/dist ./dist

USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000/ > /dev/null 2>&1 || exit 1

# -s : toutes les routes retombent sur index.html — sinon un rechargement sur
# /login renverrait un 404, le routage étant côté client (react-router).
CMD ["serve", "-s", "dist", "-l", "3000"]
