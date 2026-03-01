# Radicale Dockerfile for Hop3
# Simple CalDAV and CardDAV server

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Install Radicale
RUN python3 -m venv /opt/radicale \
    && /opt/radicale/bin/pip install --no-cache-dir radicale passlib[bcrypt]

# Create default config
RUN echo '[server]\n\
hosts = 0.0.0.0:8080\n\
\n\
[auth]\n\
type = htpasswd\n\
htpasswd_filename = /etc/radicale/users\n\
htpasswd_encryption = bcrypt\n\
\n\
[storage]\n\
filesystem_folder = /var/lib/radicale/collections\n\
\n\
[web]\n\
type = internal\n\
\n\
[logging]\n\
level = info\n\
' > /etc/radicale/config

# Copy startup script
COPY start-radicale.sh /usr/local/bin/start-radicale.sh
RUN chmod +x /usr/local/bin/start-radicale.sh

# Environment (PORT is required, no default)

# Data volume
VOLUME /var/lib/radicale/collections

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-radicale.sh"]
