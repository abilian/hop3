# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# Dockerfile for Hop3 End-to-End Tests
# This creates a container with a full Hop3 server environment including systemd

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install systemd and basic utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        systemd \
        systemd-sysv \
        ca-certificates \
        curl \
        openssh-server \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Remove unnecessary systemd services to speed up boot
RUN cd /lib/systemd/system/sysinit.target.wants/ && \
    ls | grep -v systemd-tmpfiles-setup | xargs rm -f && \
    rm -f /lib/systemd/system/multi-user.target.wants/* && \
    rm -f /etc/systemd/system/*.wants/* && \
    rm -f /lib/systemd/system/local-fs.target.wants/* && \
    rm -f /lib/systemd/system/sockets.target.wants/*udev* && \
    rm -f /lib/systemd/system/sockets.target.wants/*initctl* && \
    rm -f /lib/systemd/system/basic.target.wants/* && \
    rm -f /lib/systemd/system/anaconda.target.wants/*

# Install Hop3 dependencies (same as installer)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        # Basic tools
        bc \
        git \
        sudo \
        cron \
        build-essential \
        libpcre3-dev \
        zlib1g-dev \
        # Python
        python3 \
        python3-pip \
        python3-click \
        python3-dev \
        python3-venv \
        python3-virtualenv \
        python3-setuptools \
        # Nginx
        nginx \
        acl \
        # uwsgi
        uwsgi-core \
        uwsgi-plugin-python3 \
        # Let's Encrypt
        certbot \
        # Ruby (for test apps)
        ruby \
        ruby-dev \
        ruby-bundler \
        # Node.js (for test apps)
        npm \
        nodeenv \
        # Go (for test apps)
        golang \
        # PostgreSQL
        libpq-dev \
        postgresql \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create hop3 user
RUN useradd -m -s /bin/bash -G www-data hop3 && \
    echo "hop3:hop3" | chpasswd && \
    echo "hop3 ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Setup SSH for hop3 user
RUN mkdir -p /home/hop3/.ssh && \
    ssh-keygen -t rsa -b 4096 -f /home/hop3/.ssh/id_rsa -N "" && \
    cat /home/hop3/.ssh/id_rsa.pub >> /home/hop3/.ssh/authorized_keys && \
    chmod 700 /home/hop3/.ssh && \
    chmod 600 /home/hop3/.ssh/authorized_keys && \
    chown -R hop3:hop3 /home/hop3/.ssh

# Configure SSH server
RUN mkdir -p /var/run/sshd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' /etc/pam.d/sshd

# Copy hop3 distribution
COPY dist/hop3_server-*.tar.gz /tmp/hop3-server.tar.gz

# Install hop3 in virtual environment
RUN su - hop3 -c "python3 -m venv ~/venv && \
    ~/venv/bin/pip install --upgrade pip && \
    ~/venv/bin/pip install /tmp/hop3-server.tar.gz"

# Run hop3 setup
RUN su - hop3 -c "~/venv/bin/hop-server setup"

# Create hop3 environment file
RUN echo 'HOP3_SECRET_KEY=e2e-test-secret-key-do-not-use-in-production' > /home/hop3/.env && \
    echo 'HOP3_ENABLE_AUTH=true' >> /home/hop3/.env && \
    chown hop3:hop3 /home/hop3/.env && \
    chmod 600 /home/hop3/.env

# Create hop3-server systemd service
RUN echo '[Unit]\n\
Description=Hop3 Server\n\
After=network.target postgresql.service\n\
\n\
[Service]\n\
Type=simple\n\
User=hop3\n\
WorkingDirectory=/home/hop3\n\
EnvironmentFile=-/home/hop3/.env\n\
ExecStart=/home/hop3/venv/bin/hop-server serve\n\
Restart=always\n\
StandardOutput=journal\n\
StandardError=journal\n\
\n\
[Install]\n\
WantedBy=multi-user.target' > /etc/systemd/system/hop3-server.service

# Enable hop3-server service
RUN systemctl enable hop3-server.service && \
    systemctl enable postgresql.service && \
    systemctl enable ssh.service

# Expose ports
EXPOSE 22 80 443 8000

# Set stopsignal to SIGRTMIN+3 for proper systemd shutdown
STOPSIGNAL SIGRTMIN+3

# Volume for hop3 apps
VOLUME ["/home/hop3/apps"]

# Start systemd
CMD ["/lib/systemd/systemd"]
