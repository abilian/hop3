# CryptPad Dockerfile for Hop3
# End-to-end encrypted collaboration suite

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install Node.js and dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
ENV NODE_ENV=production

# Data volumes
VOLUME /cryptpad/datastore
VOLUME /cryptpad/data
VOLUME /cryptpad/block
VOLUME /cryptpad/blob

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
