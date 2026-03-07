# HedgeDoc Dockerfile for Hop3
# Real-time collaborative markdown editor

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js with Corepack (for Yarn Berry)
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    && corepack enable \
    && rm -rf /var/lib/apt/lists/*

# Create hedgedoc user
RUN useradd -m -s /bin/bash hedgedoc

# Create app directory
WORKDIR /home/hedgedoc/app

# Download and build HedgeDoc
ARG HEDGEDOC_VERSION=1.10.6
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV YARN_CACHE_FOLDER=/tmp/.yarn
RUN curl -sL "https://github.com/hedgedoc/hedgedoc/archive/refs/tags/${HEDGEDOC_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && yarn install --immutable \
    && yarn run build \
    && yarn workspaces focus --production \
    && chown -R hedgedoc:hedgedoc /home/hedgedoc

# Copy configuration template
COPY --chown=hedgedoc:hedgedoc config.json.template config.json

# Create uploads directory
RUN mkdir -p /home/hedgedoc/app/public/uploads \
    && chown -R hedgedoc:hedgedoc /home/hedgedoc/app/public/uploads

# Environment variables (Hop3 uses 8080 as standard container port)
# Environment (PORT and database vars are required, no defaults)
# App config with safe defaults
ENV CMD_DOMAIN=localhost
ENV CMD_URL_ADDPORT=false
ENV CMD_PROTOCOL_USESSL=false
ENV CMD_ALLOW_ANONYMOUS=true
ENV CMD_ALLOW_ANONYMOUS_EDITS=true
ENV CMD_IMAGE_UPLOAD_TYPE=filesystem
ENV CMD_UPLOADS_PATH=./public/uploads

# Copy startup script
USER root
COPY start-hedgedoc.sh /usr/local/bin/start-hedgedoc.sh
RUN chmod +x /usr/local/bin/start-hedgedoc.sh

EXPOSE 8080

CMD ["/usr/local/bin/start-hedgedoc.sh"]
