# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web-build
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY web web
RUN corepack enable \
    && pnpm install --frozen-lockfile --prod=false \
    && pnpm --filter @sdpstudio/web install --frozen-lockfile --prod=false
RUN pnpm --filter @sdpstudio/web build

FROM python:3.12-slim AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY python python
COPY alembic.ini ./
COPY migrations migrations
COPY --from=web-build /src/python/sdpstudio_server/static/react python/sdpstudio_server/static/react
RUN pip install --no-cache-dir ".[postgres]" && useradd --create-home --uid 10001 sdpstudio \
    && mkdir -p /data && chown -R 10001:10001 /app /data
USER sdpstudio
ENV SDPSTUDIO_DATA_ROOT=/data
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health')"
ENTRYPOINT ["sdpstudio"]
FROM runtime-base AS server
CMD ["serve", "--host", "0.0.0.0", "--port", "8787"]

FROM runtime-base AS worker
CMD ["worker", "--runs-only"]

# Kept as a separately addressable release target for provider runner images.
FROM runtime-base AS runner
CMD ["runner"]
