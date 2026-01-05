# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Dockerfile for Hop3 Development Environment
# Builds hop3-server inside Docker - no pre-build needed!

FROM ubuntu:24.04

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

# Install Hop3 dependencies + build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Basic tools
        bc \
        git \
        sudo \
        build-essential \
        pkg-config \
        # Python + build tools
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-setuptools \
        python3-wheel \
        # Libraries
        libffi-dev \
        libssl-dev \
        # Nginx
        nginx \
        # PostgreSQL
        postgresql \
        postgresql-client \
        libpq-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv (modern Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Create hop3 user
RUN useradd -m -s /bin/bash hop3 && \
    echo "hop3:hop3" | chpasswd && \
    echo "hop3 ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

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

# Copy hop3 source code
COPY packages/hop3-server /tmp/hop3-server-src
COPY pyproject.toml /tmp/

# Build and install hop3 with uwsgi (all in one layer)
# Note: venv is built into Python 3.3+, no separate virtualenv package needed
RUN cd /tmp/hop3-server-src && \
    python3 -m venv /home/hop3/venv && \
    /home/hop3/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /home/hop3/venv/bin/pip install --no-cache-dir . && \
    /home/hop3/venv/bin/pip install --no-cache-dir uwsgi && \
    chown -R hop3:hop3 /home/hop3/venv && \
    rm -rf /tmp/hop3-server-src /tmp/pyproject.toml

# Create hop3 environment file
RUN echo 'HOP3_ROOT=/home/hop3/.hop3' > /home/hop3/.env && \
    echo 'HOP3_SECRET_KEY=dev-secret-key-change-in-production' >> /home/hop3/.env && \
    echo 'HOP3_ENABLE_AUTH=false' >> /home/hop3/.env && \
    echo 'HOP3_DB_URL=sqlite:////home/hop3/.hop3/hop3.db' >> /home/hop3/.env && \
    echo 'ACME_ENGINE=self-signed' >> /home/hop3/.env && \
    chown hop3:hop3 /home/hop3/.env && \
    chmod 600 /home/hop3/.env

# Initialize PostgreSQL (remove existing data first if present)
RUN rm -rf /var/lib/postgresql/14/main && \
    mkdir -p /var/lib/postgresql/14/main && \
    chown -R postgres:postgres /var/lib/postgresql && \
    su - postgres -c "/usr/lib/postgresql/14/bin/initdb -D /var/lib/postgresql/14/main" && \
    echo "host all all 0.0.0.0/0 md5" >> /etc/postgresql/14/main/pg_hba.conf && \
    echo "listen_addresses = '*'" >> /etc/postgresql/14/main/postgresql.conf

# Pre-create .hop3 directories with correct ownership
RUN mkdir -p /home/hop3/.hop3/certificates && \
    chown -R hop3:hop3 /home/hop3/.hop3

# Run hop3 setup and ensure ownership
RUN su - hop3 -c "export HOP3_ROOT='/home/hop3/.hop3' && \
    export HOP3_SECRET_KEY='dev-secret-key-change-in-production' && \
    export HOP3_ENABLE_AUTH='false' && \
    export HOP3_DB_URL='sqlite:////home/hop3/.hop3/hop3.db' && \
    export ACME_ENGINE='self-signed' && \
    ~/venv/bin/hop3-server setup" && \
    chown -R hop3:hop3 /home/hop3

# Configure nginx to load hop3 app configs
# Insert include directive inside http block (after sites-enabled include)
# Note: No default site needed - app configs will handle all requests
RUN sed -i '/include \/etc\/nginx\/sites-enabled\/\*/a\    include /home/hop3/.hop3/nginx/*.conf;' /etc/nginx/nginx.conf && \
    rm -f /etc/nginx/sites-enabled/default

# Copy supervisor config
COPY dev-env/supervisord.conf /etc/supervisor/supervisord.conf

# Create log directory
RUN mkdir -p /var/log/supervisor

# Expose ports
EXPOSE 22 80 443 8000

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
