FROM python:3.13 AS builder

RUN pip install --no-cache-dir uv==0.12.4

WORKDIR /builder/apps/api

# Install backend dependencies from the locked uv dependency graph.
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
COPY packages/masterbrain/pyproject.toml packages/masterbrain/README.md packages/masterbrain/LICENSE /builder/packages/masterbrain/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Keep locked third-party installation cached across AI source edits.
ARG UV_CONCURRENT_DOWNLOADS=8
RUN --mount=type=cache,id=airalogy-api-uv,target=/root/.cache/uv \
    UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300 \
    uv sync --frozen --no-dev --no-install-project --no-install-package masterbrain --no-editable

COPY packages/masterbrain/src /builder/packages/masterbrain/src
RUN --mount=type=cache,id=airalogy-api-uv,target=/root/.cache/uv \
    UV_LINK_MODE=copy UV_HTTP_TIMEOUT=300 \
    uv sync --frozen --no-dev --no-install-project --no-editable


# run stage
FROM python:3.13-slim

ARG PLATFORM_VERSION=development
ARG GIT_COMMIT=unknown
ARG GIT_TAG=
ARG BUILD_TIME=
ARG BUILD_DIRTY=false

LABEL org.opencontainers.image.title="Airalogy Platform API" \
      org.opencontainers.image.source="https://github.com/airalogy/platform" \
      org.opencontainers.image.version="$PLATFORM_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT"

ENV PLATFORM_VERSION=$PLATFORM_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    GIT_TAG=$GIT_TAG \
    BUILD_TIME=$BUILD_TIME \
    BUILD_DIRTY=$BUILD_DIRTY

# retrieve packages from build stage
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Add a non-root user and pre-create writable volume mount points. Docker copies
# these ownership bits into newly created named volumes.
RUN useradd -ms /bin/bash deploy && \
    install -d -o deploy -g deploy /home/deploy/app/log /home/deploy/app/protocols && \
    install -o deploy -g deploy -m 0600 /dev/null /home/deploy/app/protocol_executor.log
USER deploy
WORKDIR /home/deploy/app

RUN mkdir -p log protocols

COPY --chown=deploy:deploy apps/api/ .

RUN printf '{"version":"%s","tag":"%s","commit":"%s","build_time":"%s","dirty":%s}\n' \
    "$PLATFORM_VERSION" "$GIT_TAG" "$GIT_COMMIT" "$BUILD_TIME" "$BUILD_DIRTY" \
    > app/build-info.json

# Import the actual route tree using only locked production dependencies.
# This performs no startup/lifespan work and cannot contact external services.
RUN --network=none APP_ENV=development \
    DATABASE_URL=postgresql+asyncpg://build:build@127.0.0.1/build \
    SECRET_KEY=build-only-not-a-runtime-credential \
    AES_KEY=00000000000000000000000000000000 \
    AIRALOGY_ENDPOINT=http://127.0.0.1 REDIS_URL=redis://127.0.0.1:6379/0 \
    python3 -c "from app.main import app; assert app.routes"
