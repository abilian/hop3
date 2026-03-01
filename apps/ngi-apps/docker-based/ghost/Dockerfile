# Ghost Dockerfile for Hop3
# Node.js publishing platform

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install build tools, envsubst, and Node.js 18 LTS (Ghost 5.74.x requires Node 18.x)
ARG NODE_VERSION=18.20.5
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gettext-base \
    build-essential \
    python3 \
    xz-utils \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
       | tar -xJ -C /usr/local --strip-components=1 \
    && rm -rf /var/lib/apt/lists/*

# Create ghost user and app directory
RUN useradd -m -s /bin/bash ghost
WORKDIR /home/ghost/app
RUN chown ghost:ghost /home/ghost/app

# Install Ghost CLI
RUN npm install -g ghost-cli@latest

# Install Ghost (as ghost user)
USER ghost
ARG GHOST_VERSION=5.74.5
RUN ghost install ${GHOST_VERSION} local --no-start --no-setup --dir /home/ghost/app

# Copy configuration template (processed at runtime by startup script)
COPY --chown=ghost:ghost config.production.json.template config.production.json.template

# Create content directories
RUN mkdir -p content/data content/images content/logs content/themes content/adapters

USER root

# Create startup script that configures Ghost from environment
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/ghost/app\n\
\n\
# Set defaults for config vars (Hop3 injects MYSQL_* vars)\n\
export MYSQL_HOST="${MYSQL_HOST:-localhost}"\n\
export MYSQL_PORT="${MYSQL_PORT:-3306}"\n\
export MYSQL_USER="${MYSQL_USER:-ghost}"\n\
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"\n\
export MYSQL_DATABASE="${MYSQL_DATABASE:-ghost}"\n\
export GHOST_PORT="${PORT:-8080}"\n\
export GHOST_URL="${GHOST_URL:-http://localhost:${GHOST_PORT}}"\n\
export GHOST_LOG_LEVEL="${GHOST_LOG_LEVEL:-info}"\n\
export GHOST_CONTENT_PATH="${GHOST_CONTENT_PATH:-./content}"\n\
\n\
# Process config template with envsubst\n\
envsubst < config.production.json.template > config.production.json\n\
chown ghost:ghost config.production.json\n\
\n\
# Run Ghost as ghost user\n\
exec su ghost -c "cd /home/ghost/app && node current/index.js"\n\
' > /usr/local/bin/start-ghost.sh \
    && chmod +x /usr/local/bin/start-ghost.sh

# Default port (Hop3 uses 8080 as standard container port)
ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-ghost.sh"]
