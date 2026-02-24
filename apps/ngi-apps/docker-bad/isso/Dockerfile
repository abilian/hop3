# Isso Dockerfile for Hop3
# Lightweight commenting system

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libffi-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create isso user
RUN useradd -m -d /var/lib/isso -s /bin/bash isso

# Create directories
RUN mkdir -p /var/lib/isso/db /etc/isso \
    && chown -R isso:isso /var/lib/isso /etc/isso

# Install Isso
RUN python3 -m venv /opt/isso \
    && /opt/isso/bin/pip install --no-cache-dir isso gunicorn

# Create default config
RUN echo '[general]\n\
dbpath = /var/lib/isso/db/comments.db\n\
host = http://localhost:8080\n\
\n\
[server]\n\
listen = http://0.0.0.0:8080\n\
\n\
[moderation]\n\
enabled = false\n\
\n\
[guard]\n\
enabled = true\n\
ratelimit = 2\n\
direct-reply = 3\n\
reply-to-self = false\n\
require-author = false\n\
require-email = false\n\
\n\
[markup]\n\
options = strikethrough, superscript, autolink\n\
allowed-elements = \n\
allowed-attributes = \n\
\n\
[hash]\n\
salt = change-me-to-random-string\n\
algorithm = pbkdf2\n\
' > /etc/isso/isso.cfg \
    && chown isso:isso /etc/isso/isso.cfg

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Configuration\n\
export ISSO_PORT="${PORT:-8080}"\n\
export ISSO_HOST="${ISSO_HOST:-http://localhost:${ISSO_PORT}}"\n\
export ISSO_SALT="${ISSO_SALT:-$(head -c 16 /dev/urandom | base64)}"\n\
\n\
# Update config\n\
sed -i "s|host = .*|host = ${ISSO_HOST}|" /etc/isso/isso.cfg\n\
sed -i "s|listen = .*|listen = http://0.0.0.0:${ISSO_PORT}|" /etc/isso/isso.cfg\n\
sed -i "s|salt = .*|salt = ${ISSO_SALT}|" /etc/isso/isso.cfg\n\
\n\
# Ensure proper ownership\n\
chown -R isso:isso /var/lib/isso\n\
\n\
# Run Isso as isso user\n\
exec su isso -c "/opt/isso/bin/isso -c /etc/isso/isso.cfg run"\n\
' > /usr/local/bin/start-isso.sh \
    && chmod +x /usr/local/bin/start-isso.sh

# Environment
ENV PORT=8080

# Data volume
VOLUME /var/lib/isso/db

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-isso.sh"]
