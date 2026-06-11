# Ghost Blogging Platform (Docker-based)
# Modern publishing platform for professional bloggers
# https://ghost.org/
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim

# Install Node.js 20 LTS and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create ghost user
RUN useradd -m -d /var/lib/ghost -s /bin/bash ghost

# Ghost version
ARG GHOST_VERSION=5.111.0

# Install Ghost CLI and create Ghost installation
WORKDIR /var/lib/ghost
RUN npm install -g ghost-cli@latest \
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
