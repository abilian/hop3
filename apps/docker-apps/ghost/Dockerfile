# Ghost Dockerfile for Hop3
# Node.js publishing platform

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install build tools, envsubst, and Node.js from Debian repos
# Debian trixie has Node.js 18+ which Ghost supports
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gettext-base \
    build-essential \
    python3 \
    nodejs \
    npm \
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

# Copy startup script
COPY start-ghost.sh /usr/local/bin/start-ghost.sh
RUN chmod +x /usr/local/bin/start-ghost.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start-ghost.sh"]
