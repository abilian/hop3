# Radicale Dockerfile for Hop3
# Simple CalDAV and CardDAV server

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    apache2-utils \
    && rm -rf /var/lib/apt/lists/*

# Create radicale user
RUN useradd -m -d /var/lib/radicale -s /bin/bash radicale

# Create directories
RUN mkdir -p /var/lib/radicale/collections /etc/radicale \
    && chown -R radicale:radicale /var/lib/radicale /etc/radicale

# Install Radicale and gettext-base for envsubst
RUN apt-get update -q && apt-get install -q -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/radicale \
    && /opt/radicale/bin/pip install --no-cache-dir radicale passlib[bcrypt]

# Copy config template (envsubst generates final config at runtime)
COPY radicale.cfg.template /etc/radicale/config.template
RUN chown radicale:radicale /etc/radicale/config.template

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)

# Data volume
VOLUME /var/lib/radicale/collections

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
