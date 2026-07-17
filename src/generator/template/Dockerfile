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

# Règle d'or du Chap 21 : jamais de conteneur en root. appuser n'a aucun droit
# d'écriture sur le code qu'il exécute — une faille applicative reste confinée.
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

# /app reste root (code en lecture seule pour appuser — règle Chap 21). Les
# écritures runtime vont dans /data, seul emplacement inscriptible : SQLite d'un
# T0, uploads éventuels. En T1/T2 la base est distante (Postgres), /data sert de
# repli sûr plutôt que de laisser l'app tenter d'écrire dans /app (échec).
RUN mkdir -p /data && chown appuser:appuser /data
VOLUME /data

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GITSKY_DATA_DIR=/data

USER appuser

EXPOSE 8000

# Traefik n'envoie du trafic qu'à un conteneur sain (Chap 21). On sonde /health
# avec Python (déjà présent) plutôt que curl : pas de paquet apt supplémentaire,
# image plus légère, et urlopen lève sur un 503 -> conteneur marqué non sain.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; import sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"]

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
