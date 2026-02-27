# Wekan Dockerfile for Hop3
# Open source Kanban board (Trello alternative)
# NOTE: This bundles MongoDB as Hop3 doesn't yet have a MongoDB addon

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies (build-essential needed for node-fibers compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    gosu \
    unzip \
    build-essential \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Install MongoDB 7.0
RUN curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
    gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor \
    && echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] http://repo.mongodb.org/apt/debian bookworm/mongodb-org/7.0 main" | \
    tee /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update \
    && apt-get install -y mongodb-org \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 14.x (Wekan requires Node 14 for fibers compatibility)
RUN curl -fsSL https://deb.nodesource.com/setup_14.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create wekan user
RUN useradd -m -d /home/wekan -s /bin/bash wekan

# Create directories
RUN mkdir -p /data/db /home/wekan/app /var/log/mongodb \
    && chown -R wekan:wekan /home/wekan \
    && chown -R mongodb:mongodb /data/db /var/log/mongodb

WORKDIR /home/wekan/app

# Download Wekan from GitHub releases (detect architecture at build time)
ARG WEKAN_VERSION=v8.34
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL -L "https://github.com/wekan/wekan/releases/download/${WEKAN_VERSION}/wekan-${WEKAN_VERSION#v}-${ARCH}.zip" -o /tmp/wekan.zip \
    && unzip -q /tmp/wekan.zip -d /home/wekan/app \
    && rm /tmp/wekan.zip \
    && chown -R wekan:wekan /home/wekan/app

# Install Node dependencies (fibers pre-built for Node 14)
WORKDIR /home/wekan/app/bundle/programs/server
RUN npm install --production --unsafe-perm

WORKDIR /home/wekan/app

# Create startup script
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    '# Start MongoDB in background' \
    'mongod --dbpath /data/db --logpath /var/log/mongodb/mongod.log --fork --bind_ip 127.0.0.1' \
    '' \
    '# Wait for MongoDB to start' \
    'sleep 3' \
    'until mongosh --eval "db.adminCommand({ping: 1})" > /dev/null 2>&1; do' \
    '    echo "Waiting for MongoDB..."' \
    '    sleep 1' \
    'done' \
    '' \
    '# Configuration' \
    'export PORT="${PORT:-8080}"' \
    'export ROOT_URL="${ROOT_URL:-http://localhost:${PORT}}"' \
    'export MONGO_URL="mongodb://127.0.0.1:27017/wekan"' \
    'export MAIL_URL="${MAIL_URL:-}"' \
    'export MAIL_FROM="${MAIL_FROM:-wekan@localhost}"' \
    '' \
    '# Wekan settings' \
    'export WITH_API=true' \
    'export RICHER_CARD_COMMENT_EDITOR=false' \
    'export BROWSER_POLICY_ENABLED=true' \
    '' \
    '# Ensure proper ownership' \
    'chown -R wekan:wekan /home/wekan' \
    '' \
    '# Run Wekan as wekan user' \
    'cd /home/wekan/app/bundle' \
    'exec gosu wekan node main.js' \
    > /usr/local/bin/start-wekan.sh \
    && chmod +x /usr/local/bin/start-wekan.sh

# Environment
ENV PORT=8080
ENV NODE_ENV=production

# Data volumes
VOLUME /data/db

EXPOSE 8080

CMD ["/usr/local/bin/start-wekan.sh"]
