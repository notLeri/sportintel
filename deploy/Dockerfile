# syntax=docker/dockerfile:1.7
# Один образ — роли web | worker | migrate (ARCHITECTURE §29.1, INFRA-T0.10).

# ---------- frontend ----------
FROM node:22-alpine AS fe-build
ARG VERSION=dev
ENV VITE_VERSION=${VERSION}
RUN corepack enable
WORKDIR /fe
# pnpm-workspace.yaml — разрешённые install-скрипты (pnpm 10+ без него падает); версию pnpm
# corepack берёт из packageManager в package.json
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# tsc -b проверяет и тесты; общий с backend кейс длины Telegram-поста лежит в /fixtures репозитория
COPY fixtures/telegram/ /fixtures/telegram/
RUN pnpm build \
 && mkdir -p /maps \
 && find dist -name '*.map' -exec sh -c 'mkdir -p "/maps/$(dirname "$1")" && mv "$1" "/maps/$1"' _ {} \;

# Source maps — отдельная цель для загрузки в Sentry: docker build --target fe-maps -o out .
FROM scratch AS fe-maps
COPY --from=fe-build /maps /

# ---------- backend ----------
FROM python:3.12-slim AS be-build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Сначала lock-файлы: слой зависимостей кэшируется, пока они не меняются.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim AS runtime
ARG VERSION=dev
ENV VERSION=${VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    STATIC_DIR=/app/static \
    PORT=8000
RUN apt-get update \
 && apt-get install -y --no-install-recommends libxml2 libxslt1.1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=be-build /app/.venv ./.venv
COPY --from=be-build /app/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY --from=fe-build /fe/dist ./static
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
