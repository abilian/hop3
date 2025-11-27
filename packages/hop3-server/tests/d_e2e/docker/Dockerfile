# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Simplified Dockerfile for Hop3 E2E Tests (works on macOS)
# This version doesn't use systemd - services are started manually
#
# LAYER OPTIMIZATION:
# Layers are ordered from least-frequently-changing to most-frequently-changing
# to maximize Docker cache reuse during rebuilds.

FROM ubuntu:24.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# =============================================================================
# LAYER 1: System packages (rarely change)
# =============================================================================

# Install basic utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        openssh-server \
        supervisor \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Hop3 dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Basic tools
        bc \
        git \
        sudo \
        build-essential \
        pkg-config \
        libpcre3-dev \
        zlib1g-dev \
        wget \
        # Python
        python3 \
        python3-pip \
        python3-venv \
        python3-virtualenv \
        python3-dev \
        python3-setuptools \
        python3-wheel \
        # Libraries needed for Python packages
        libffi-dev \
        libssl-dev \
        # Nginx
        nginx \
        acl \
        # uWSGI
        uwsgi-core \
        uwsgi-plugin-python3 \
        # PostgreSQL
        postgresql \
        postgresql-client \
        libpq-dev \
        # Language runtimes for builders
        # - Ruby
        ruby \
        ruby-dev \
        ruby-bundler \
        # - Node.js
        npm \
        nodeenv \
        yarnpkg \
        # - Go
        golang \
        # - Clojure
        clojure \
        leiningen \
        # Extra libraries
        libcairo2 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Caddy (for proxy plugin testing)
# Using official Caddy repository for Ubuntu
RUN apt-get update && \
    apt-get install -y --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https gnupg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg && \
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends caddy && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Traefik (for proxy plugin testing)
# Download static binary from official releases
RUN wget -q https://github.com/traefik/traefik/releases/download/v2.11.0/traefik_v2.11.0_linux_amd64.tar.gz -O /tmp/traefik.tar.gz && \
    tar -xzf /tmp/traefik.tar.gz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/traefik && \
    rm /tmp/traefik.tar.gz && \
    mkdir -p /etc/traefik /etc/traefik/dynamic

# =============================================================================
# LAYER 2: User and SSH setup (rarely change)
# =============================================================================

# Create hop3 user and add www-data to hop3 group for socket access
RUN useradd -m -s /bin/bash hop3 && \
    echo "hop3:hop3" | chpasswd && \
    echo "hop3 ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    usermod -a -G hop3 www-data

# Setup SSH
RUN mkdir -p /var/run/sshd && \
    mkdir -p /home/hop3/.ssh && \
    ssh-keygen -t rsa -b 2048 -f /home/hop3/.ssh/id_rsa -N "" && \
    cat /home/hop3/.ssh/id_rsa.pub >> /home/hop3/.ssh/authorized_keys && \
    chmod 700 /home/hop3/.ssh && \
    chmod 600 /home/hop3/.ssh/authorized_keys && \
    chown -R hop3:hop3 /home/hop3/.ssh

# Configure SSH
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' /etc/pam.d/sshd

# =============================================================================
# LAYER 3: Python dependencies (change when pyproject.toml changes)
# =============================================================================

# Create virtualenv first (this layer is stable)
RUN su - hop3 -c "python3 -m venv ~/venv && \
    ~/venv/bin/pip install --no-cache-dir --upgrade pip"

# Copy ONLY pyproject.toml and README.md first to install dependencies
# This layer is cached as long as dependencies don't change
COPY packages/hop3-server/pyproject.toml /opt/hop3-server/pyproject.toml
COPY packages/hop3-server/README.md /opt/hop3-server/README.md

# Create minimal package structure needed for pip install
RUN mkdir -p /opt/hop3-server/src/hop3 && \
    echo '__version__ = "0.0.0"' > /opt/hop3-server/src/hop3/__init__.py && \
    chown -R hop3:hop3 /opt/hop3-server

# Install dependencies (this is the expensive step - now cached!)
RUN su - hop3 -c "~/venv/bin/pip install --no-cache-dir -e /opt/hop3-server"

# =============================================================================
# LAYER 4: Application code (changes frequently)
# =============================================================================

# Now copy the actual source code
COPY packages/hop3-server/src /opt/hop3-server/src
RUN rm -rf /opt/hop3-server/src/hop3/__pycache__ && \
    chown -R hop3:hop3 /opt/hop3-server/src

# =============================================================================
# LAYER 5: Configuration and setup (changes rarely)
# =============================================================================

# Create hop3 environment file
RUN echo 'HOP3_SECRET_KEY=e2e-test-secret-key-do-not-use-in-production' > /home/hop3/.env && \
    echo 'HOP3_UNSAFE=true' >> /home/hop3/.env && \
    echo 'HOP3_DB_URL=sqlite:////home/hop3/hop3.db' >> /home/hop3/.env && \
    echo 'ACME_ENGINE=self-signed' >> /home/hop3/.env && \
    chown hop3:hop3 /home/hop3/.env && \
    chmod 600 /home/hop3/.env

# Run hop3 setup with environment variables
RUN su - hop3 -c "export HOP3_SECRET_KEY='e2e-test-secret-key-do-not-use-in-production' && \
    export HOP3_UNSAFE='true' && \
    export HOP3_DB_URL='sqlite:////home/hop3/hop3.db' && \
    export ACME_ENGINE='self-signed' && \
    ~/venv/bin/hop-server setup"

# Configure nginx to include hop3 configs
RUN echo 'include /home/hop3/nginx/*.conf;' > /etc/nginx/sites-enabled/hop3 && \
    rm -f /etc/nginx/sites-enabled/default

# Create log directory for supervisor
RUN mkdir -p /var/log/supervisor

# Copy and setup entrypoint script that configures supervisord based on HOP3_PROXY_TYPE
COPY packages/hop3-server/tests/d_e2e/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose ports
EXPOSE 22 80 443 8000

# Use entrypoint script to dynamically configure proxy based on HOP3_PROXY_TYPE
CMD ["/entrypoint.sh"]
