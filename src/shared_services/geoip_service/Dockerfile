FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le paquet sous /app/geoip_service (import package conservé).
COPY . ./geoip_service

CMD ["uvicorn", "geoip_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
