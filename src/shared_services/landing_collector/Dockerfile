FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le paquet sous /app/landing_collector (import package conservé).
COPY . ./landing_collector

CMD ["uvicorn", "landing_collector.main:app", "--host", "0.0.0.0", "--port", "8000"]
