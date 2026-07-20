# Isso Dockerfile for Hop3
# Lightweight commenting system

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (python3-setuptools provides pkg_resources for Python 3.13)
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    build-essential \
    libffi-dev \
    sqlite3 \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Create isso user
RUN useradd -m -d /var/lib/isso -s /bin/bash isso

# Create directories
RUN mkdir -p /var/lib/isso/db /etc/isso \
    && chown -R isso:isso /var/lib/isso /etc/isso

# Install Isso in venv with system site-packages (for pkg_resources access)
RUN python3 -m venv --system-site-packages /opt/isso \
    && /opt/isso/bin/pip install --no-cache-dir isso gunicorn

# Copy config template (envsubst generates final config at runtime)
COPY isso.cfg.template /etc/isso/isso.cfg.template
RUN chown isso:isso /etc/isso/isso.cfg.template

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)

# Data volume
VOLUME /var/lib/isso/db

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
