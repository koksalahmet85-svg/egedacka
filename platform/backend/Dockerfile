# Prisma CLI Node ister: resmi Node imajından kopyalanır (apt ve nodeenv gerekmez).
FROM node:22-slim AS node

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PRISMA_BINARY_CACHE_DIR=/opt/prisma/binaries \
    PRISMA_NODEENV_CACHE_DIR=/opt/prisma/nodeenv \
    HOME=/tmp
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY prisma ./prisma
# Python istemcisi, Prisma CLI ve sorgu motoru imaja gömülür (çalışma anında indirme yok).
RUN prisma generate
COPY app ./app

FROM base AS runtime
RUN useradd --uid 10001 --no-create-home app && mkdir -p /opt/prisma && chown -R app /app /opt/prisma /tmp
USER app
EXPOSE 8000
# Migration ayrı "migrate" servisinde yapılır; API birden çok worker ile güvenle ölçeklenir.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
