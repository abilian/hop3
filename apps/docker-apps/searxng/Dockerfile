# SearXNG Dockerfile for Hop3
# Privacy-respecting metasearch engine

FROM debian:trixie-slim

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

# Clone SearXNG
RUN git clone --depth 1 https://github.com/searxng/searxng.git /usr/local/searxng/searxng-src \
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
