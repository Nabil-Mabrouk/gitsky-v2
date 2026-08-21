# Image jetable pour lancer le pipeline Studio (Chap 24) — pas un service
# persistant. Construire depuis CE dossier (studio/) comme contexte, puis :
#
#   docker run --rm --network shared-services-net \
#     -e LLM_PROXY_URL=http://llm-proxy:4000 \
#     -e LLM_PROXY_TOKEN=<LITELLM_MASTER_KEY> \
#     -v /opt/gitsky/configs:/out \
#     gitsky-studio --project ... --idea ... --domain ... --out-dir /out
#
# Copié dans /app/studio/ (pas /app/ directement) : les imports absolus
# (from studio.xxx import ...), déjà utilisés par les tests
# (sys.path.insert sur le PARENT de studio/), exigent que le paquet
# s'appelle "studio" depuis la racine du sys.path — WORKDIR /app la fournit.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./studio/
ENTRYPOINT ["python", "-m", "studio.run_studio"]
