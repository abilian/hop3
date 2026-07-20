# GlitchTip Dockerfile for Hop3
# Django + PostgreSQL + Redis. GlitchTip 6.x uses PEP-621 [project]
# deps + uv.lock; we use uv sync which is ~10x faster than pip for
# this size of dep tree (boto3, opentelemetry, duckdb, symbolic, …).

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libssl-dev \
    libffi-dev \
    build-essential \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv from the official standalone installer (faster than pip-based).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

RUN useradd -m -s /bin/bash glitchtip

WORKDIR /opt/glitchtip

ARG GLITCHTIP_VERSION=6.1.5
RUN curl -fsSL "https://gitlab.com/glitchtip/glitchtip-backend/-/archive/v${GLITCHTIP_VERSION}/glitchtip-backend-v${GLITCHTIP_VERSION}.tar.gz" \
    | tar xz --strip-components=1

# uv sync from the committed uv.lock — frozen, no-dev for production.
RUN python3 -m venv /opt/glitchtip/venv \
    && UV_PROJECT_ENVIRONMENT=/opt/glitchtip/venv \
       uv sync --frozen --no-dev --no-install-project

ENV PATH="/opt/glitchtip/venv/bin:${PATH}"

RUN mkdir -p /data && chown -R glitchtip:glitchtip /opt/glitchtip /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
