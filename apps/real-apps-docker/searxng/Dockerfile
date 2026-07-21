# SearXNG Dockerfile for Hop3
# Privacy-respecting metasearch engine

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (including all build deps for Python packages)
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libxslt1-dev \
    libxml2-dev \
    libffi-dev \
    libssl-dev \
    libyaml-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    libbrotli-dev \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create searxng user
RUN useradd -m -d /usr/local/searxng -s /bin/bash searxng

# Create directories
RUN mkdir -p /usr/local/searxng /etc/searxng \
    && chown -R searxng:searxng /usr/local/searxng /etc/searxng

WORKDIR /usr/local/searxng

# Clone SearXNG, pinned to an exact commit. SearXNG is a rolling release with no
# tags, so a bare `git clone --depth 1` floats upstream HEAD and the build is not
# reproducible. Fetch the pinned SHA directly (shallow); bump SEARXNG_COMMIT to
# upgrade. Pins the source tree AND its requirements.txt.
ARG SEARXNG_COMMIT=6da6eee265daeb4a62ab638d6921522bf405de69
RUN mkdir -p /usr/local/searxng/searxng-src \
    && cd /usr/local/searxng/searxng-src \
    && git init -q \
    && git remote add origin https://github.com/searxng/searxng.git \
    && git fetch -q --depth 1 origin "${SEARXNG_COMMIT}" \
    && git checkout -q FETCH_HEAD \
    && chown -R searxng:searxng /usr/local/searxng

# Create venv and install
# Note: --no-build-isolation needed because searx/__init__.py imports msgspec at setup time
RUN python3 -m venv /usr/local/searxng/venv \
    && /usr/local/searxng/venv/bin/pip install --no-cache-dir -U pip setuptools wheel \
    && /usr/local/searxng/venv/bin/pip install --no-cache-dir -q -r /usr/local/searxng/searxng-src/requirements.txt \
    && /usr/local/searxng/venv/bin/pip install --no-cache-dir -q --no-build-isolation /usr/local/searxng/searxng-src

# Install gettext-base for envsubst
RUN apt-get update -q && apt-get install -q -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Copy settings template (envsubst generates final config at runtime)
COPY settings.yml.template /etc/searxng/settings.yml.template
RUN chown searxng:searxng /etc/searxng/settings.yml.template

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
ENV SEARXNG_SETTINGS_PATH=/etc/searxng/settings.yml

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
