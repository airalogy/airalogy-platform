ARG EXECUTOR_PYTHON_REPOSITORY=python
# Python 3.13.5-slim, both stages use the same multi-platform index.
ARG EXECUTOR_PYTHON_DIGEST=sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419
FROM ${EXECUTOR_PYTHON_REPOSITORY}@${EXECUTOR_PYTHON_DIGEST} AS builder

WORKDIR /builder

# Local build (must match AIRALOGY_PROTOCOL_EXECUTOR_IMAGE):
# docker build -t airalogy-platform-protocol-executor:local -f protocol_executor.Dockerfile .
COPY protocol_requirements.txt ./

# set pip source
RUN pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple pip -U && \
    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# Install requirements
RUN pip install --no-cache-dir -r protocol_requirements.txt


# run stage
FROM ${EXECUTOR_PYTHON_REPOSITORY}@${EXECUTOR_PYTHON_DIGEST}

ARG PLATFORM_VERSION=development
ARG GIT_COMMIT=unknown
ARG GIT_TAG=
ARG BUILD_TIME=
ARG BUILD_DIRTY=false

LABEL org.opencontainers.image.title="Airalogy Platform Protocol Executor" \
      org.opencontainers.image.source="https://github.com/airalogy/platform" \
      org.opencontainers.image.version="$PLATFORM_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT"

ENV PLATFORM_VERSION=$PLATFORM_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    GIT_TAG=$GIT_TAG \
    BUILD_TIME=$BUILD_TIME \
    BUILD_DIRTY=$BUILD_DIRTY

# retrieve packages from build stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages

# add a no-root user
RUN useradd -ms /bin/bash deploy
USER deploy
WORKDIR /home/deploy/app
