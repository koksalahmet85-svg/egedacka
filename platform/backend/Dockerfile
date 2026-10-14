FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PRISMA_BINARY_CACHE_DIR=/opt/prisma-cache
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY prisma ./prisma
# Python istemcisi + sorgu motoru ikilileri imaja gömülür (çalışma anında indirme yok).
RUN prisma generate && prisma py fetch
COPY app ./app

FROM base AS runtime
RUN useradd --uid 10001 --no-create-home app && chown -R app /app /opt/prisma-cache
USER app
EXPOSE 8000
# Migration ayrı "migrate" servisinde yapılır; API birden çok worker ile güvenle ölçeklenir.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
