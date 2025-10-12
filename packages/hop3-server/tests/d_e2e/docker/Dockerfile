# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Simplified Dockerfile for Hop3 E2E Tests (works on macOS)
# This version doesn't use systemd - services are started manually

FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

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

# Copy and install hop3
COPY dist/hop3_server-*.tar.gz /tmp/hop3-server.tar.gz
RUN su - hop3 -c "python3 -m venv ~/venv && \
    ~/venv/bin/pip install --no-cache-dir --upgrade pip && \
    ~/venv/bin/pip install --no-cache-dir /tmp/hop3-server.tar.gz" && \
    rm /tmp/hop3-server.tar.gz

# Create hop3 environment file
RUN echo 'HOP3_SECRET_KEY=e2e-test-secret-key-do-not-use-in-production' > /home/hop3/.env && \
    echo 'HOP3_ENABLE_AUTH=false' >> /home/hop3/.env && \
    echo 'HOP3_DB_URL=sqlite:////home/hop3/hop3.db' >> /home/hop3/.env && \
    echo 'ACME_ENGINE=self-signed' >> /home/hop3/.env && \
    chown hop3:hop3 /home/hop3/.env && \
    chmod 600 /home/hop3/.env

# Run hop3 setup with environment variables
RUN su - hop3 -c "export HOP3_SECRET_KEY='e2e-test-secret-key-do-not-use-in-production' && \
    export HOP3_ENABLE_AUTH='false' && \
    export HOP3_DB_URL='sqlite:////home/hop3/hop3.db' && \
    export ACME_ENGINE='self-signed' && \
    ~/venv/bin/hop-server setup"

# Configure nginx to include hop3 configs
RUN echo 'include /home/hop3/nginx/*.conf;' > /etc/nginx/sites-enabled/hop3 && \
    rm -f /etc/nginx/sites-enabled/default

# Create supervisor config to manage services
RUN mkdir -p /var/log/supervisor
COPY packages/hop3-server/tests/d_e2e/docker/supervisord.conf /etc/supervisor/supervisord.conf

# Expose ports
EXPOSE 22 80 443 8000

# Start supervisor (which will start SSH and hop3-server)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
