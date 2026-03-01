# CryptPad Dockerfile for Hop3
# End-to-end encrypted collaboration suite

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Node.js and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Bower globally
RUN npm install -g bower

# Create cryptpad user
RUN useradd -m -d /cryptpad -s /bin/bash cryptpad

# Create directories
RUN mkdir -p /cryptpad/data /cryptpad/datastore /cryptpad/block /cryptpad/blob /cryptpad/blobstage \
    && chown -R cryptpad:cryptpad /cryptpad

WORKDIR /cryptpad

# Clone CryptPad
ARG CRYPTPAD_VERSION=2024.6.1
RUN git clone --depth 1 --branch ${CRYPTPAD_VERSION} https://github.com/cryptpad/cryptpad.git /cryptpad/app \
    && chown -R cryptpad:cryptpad /cryptpad

# Install dependencies as cryptpad user
USER cryptpad
WORKDIR /cryptpad/app
# Note: CryptPad 2024.6.x no longer uses bower, npm handles all dependencies
RUN npm install --production

USER root

# Create config template
RUN cp /cryptpad/app/config/config.example.js /cryptpad/app/config/config.js

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Configuration\n\
export CPAD_PORT="${PORT:-8080}"\n\
export CPAD_MAIN_DOMAIN="${CPAD_MAIN_DOMAIN:-http://localhost:${CPAD_PORT}}"\n\
\n\
# Update config.js\n\
cat > /cryptpad/app/config/config.js << EOF\n\
module.exports = {\n\
    httpUnsafeOrigin: "${CPAD_MAIN_DOMAIN}",\n\
    httpSafeOrigin: "${CPAD_SANDBOX_DOMAIN:-${CPAD_MAIN_DOMAIN}}",\n\
    httpPort: ${CPAD_PORT},\n\
    httpAddress: "0.0.0.0",\n\
    \n\
    filePath: "/cryptpad/datastore",\n\
    archivePath: "/cryptpad/data/archive",\n\
    pinPath: "/cryptpad/data/pins",\n\
    taskPath: "/cryptpad/data/tasks",\n\
    blockPath: "/cryptpad/block",\n\
    blobPath: "/cryptpad/blob",\n\
    blobStagingPath: "/cryptpad/blobstage",\n\
    decreePath: "/cryptpad/data/decrees",\n\
    \n\
    logPath: false,\n\
    logToStdout: true,\n\
    logLevel: "info",\n\
    \n\
    adminKeys: [],\n\
    \n\
    defaultStorageLimit: 50 * 1024 * 1024,\n\
    \n\
    installMethod: "hop3",\n\
};\n\
EOF\n\
\n\
# Ensure proper ownership\n\
chown -R cryptpad:cryptpad /cryptpad\n\
\n\
# Run CryptPad as cryptpad user\n\
exec su cryptpad -c "cd /cryptpad/app && node server.js"\n\
' > /usr/local/bin/start-cryptpad.sh \
    && chmod +x /usr/local/bin/start-cryptpad.sh

# Environment
ENV PORT=8080
ENV NODE_ENV=production

# Data volumes
VOLUME /cryptpad/datastore
VOLUME /cryptpad/data
VOLUME /cryptpad/block
VOLUME /cryptpad/blob

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-cryptpad.sh"]
