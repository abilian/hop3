# Etherpad Dockerfile for Hop3
# Real-time collaborative editor

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    python3 \
    && corepack enable \
    && rm -rf /var/lib/apt/lists/*

# Create etherpad user
RUN useradd -m -s /bin/bash etherpad

WORKDIR /home/etherpad/app

# Download Etherpad and install dependencies
ARG ETHERPAD_VERSION=2.0.3
ENV CI=true
RUN curl -sL "https://github.com/ether/etherpad-lite/archive/refs/tags/v${ETHERPAD_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && bin/installDeps.sh \
    && chown -R etherpad:etherpad /home/etherpad

# Copy startup script
COPY start-etherpad.sh /usr/local/bin/start-etherpad.sh
RUN chmod +x /usr/local/bin/start-etherpad.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start-etherpad.sh"]
