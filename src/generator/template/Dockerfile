# Dockerfile de PRODUCTION du backend (Chap 21).
#
# UN SEUL Dockerfile pour les trois tiers : ce sont les flags du .env qui
# décident À L'EXÉCUTION des routers/modèles/migrations chargés. Passer de T1 à
# T2 = redéployer avec un .env à jour, sans rebuild.
#
# Ce fichier ne contient donc AUCUNE variable Jinja : le tier n'existe pas au
# build. Tout ce qui varie par tier (workers compris) arrive par l'environnement.
#
# Le développement garde Dockerfile.dev (hot-reload, uvicorn --reload).
# Ne pas éditer à la main : modifier le template du générateur.

# ── Stage 1 : builder ────────────────────────────────────────────────────────
# `pip install --user` concentre tout dans /root/.local : un seul dossier à
# recopier ensuite, sans traîner pip ni les outils de compilation en production.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2 : production ─────────────────────────────────────────────────────
FROM python:3.12-slim AS production

# curl est requis par le HEALTHCHECK ci-dessous.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Règle d'or du Chap 21 : jamais de conteneur en root. appuser n'a aucun droit
# d'écriture sur le code qu'il exécute — une faille applicative reste confinée.
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

# Traefik n'envoie du trafic qu'à un conteneur sain (Chap 21).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Gunicorn orchestre des workers Uvicorn et redémarre automatiquement celui qui
# tombe. Le NOMBRE de workers vient de WEB_CONCURRENCY (lu nativement par
# Gunicorn), injecté par le .env du projet : 1 en T0, 2 en T1, 4 en T2.
#
# ÉCART AU LIVRE (2 points) :
#  - le Chap 21 fige `-w 4` dans le CMD ; ce serait un artefact par tier, en
#    contradiction avec ses propres promesses (« un seul artefact à builder »,
#    « passer de T1 à T2 sans rebuild ») — d'où WEB_CONCURRENCY.
#  - le Chap 21 écrit `-k uvicorn.workers.UvicornWorker`, classe dépréciée
#    depuis uvicorn 0.30 (« use `uvicorn-worker` package instead »). On utilise
#    le paquet uvicorn-worker.
CMD ["gunicorn", "app.core.main:app", \
     "-k", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000"]
