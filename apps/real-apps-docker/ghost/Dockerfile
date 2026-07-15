# Ghost Blogging Platform (Docker-based)
# Modern publishing platform for professional bloggers
# https://ghost.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Node.js 22 LTS and dependencies.
# Ghost 5.111 requires Node "^22.13.0 || ^24.0.0"; Node 20 fails ghost-cli's
# doctor check ("version of Node.js you are using is not supported").
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create ghost user
RUN useradd -m -d /var/lib/ghost -s /bin/bash ghost

# Ghost version
ARG GHOST_VERSION=5.111.0

# Install Ghost CLI and create Ghost installation.
# Pin ghost-cli so its Node engine requirement can't drift on a future rebuild
# and silently outrun the Node version installed above.
WORKDIR /var/lib/ghost
RUN npm install -g ghost-cli@1.30.0 \
    && chown -R ghost:ghost /var/lib/ghost

# Install Ghost as ghost user
USER ghost
RUN ghost install ${GHOST_VERSION} local --no-start --no-setup \
    && npm cache clean --force

# Switch back to root for startup script
USER root

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 2368

CMD ["/start.sh"]
