# Radicale Dockerfile for Hop3
# Simple CalDAV and CardDAV server

FROM debian:bookworm-slim

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

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Configuration\n\
export RADICALE_PORT="${PORT:-8080}"\n\
export RADICALE_DATA_DIR="${RADICALE_DATA_DIR:-/var/lib/radicale/collections}"\n\
\n\
# Create default admin user if users file does not exist\n\
if [ ! -f /etc/radicale/users ]; then\n\
    ADMIN_PASSWORD="${RADICALE_ADMIN_PASSWORD:-admin}"\n\
    htpasswd -bcB /etc/radicale/users admin "${ADMIN_PASSWORD}"\n\
    chown radicale:radicale /etc/radicale/users\n\
fi\n\
\n\
# Update config with correct port\n\
sed -i "s/hosts = 0.0.0.0:8080/hosts = 0.0.0.0:${RADICALE_PORT}/" /etc/radicale/config\n\
\n\
# Ensure proper ownership\n\
chown -R radicale:radicale /var/lib/radicale\n\
\n\
# Run Radicale as radicale user\n\
exec su radicale -c "/opt/radicale/bin/radicale --config /etc/radicale/config"\n\
' > /usr/local/bin/start-radicale.sh \
    && chmod +x /usr/local/bin/start-radicale.sh

# Environment
ENV PORT=8080

# Data volume
VOLUME /var/lib/radicale/collections

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-radicale.sh"]
