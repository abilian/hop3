# Ghost Dockerfile for Hop3
# Node.js publishing platform

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install build tools + Node.js 18. Ghost 5.x rejects Node 20+ at
# install time ("Ghost v5.74.5 ... requires ^18.12.1"). Debian
# Trixie ships Node 20 so we can't rely on apt — the NodeSource
# repo would need apt pinning to override the higher default, and
# Debian's `nodejs` package doesn't bundle `npm` anyway.
# Install the official Node 18 binary tarball directly: no apt
# mess, includes npm, known-good version pinning via NODE_VERSION.
ENV NODE_VERSION=18.20.5
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    xz-utils \
    gettext-base \
    build-essential \
    python3 \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
         | tar -xJ -C /usr/local --strip-components=1 \
    && node --version && npm --version

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
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
