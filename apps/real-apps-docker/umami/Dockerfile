# Umami Dockerfile for Hop3
# Privacy-focused web analytics

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js and build tools for native modules
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -s /bin/bash umami

WORKDIR /home/umami/app

# Download and build Umami
# Umami requires DATABASE_URL at build time for Prisma
# Skip check-db step (requires actual DB connection) and run build steps individually
ARG UMAMI_VERSION=v2.10.1
ENV DATABASE_URL="postgresql://build:build@localhost:5432/build"
# Need devDependencies for build (rollup), so temporarily unset NODE_ENV
# Use --ignore-scripts to skip broken native module builds (optional deps)
RUN curl -sL "https://github.com/umami-software/umami/archive/refs/tags/${UMAMI_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && NODE_ENV=development npm install --legacy-peer-deps --ignore-scripts \
    && npm run build-db \
    && npm run build-tracker \
    && npm run build-app \
    && npm prune --production --legacy-peer-deps \
    && chown -R umami:umami /home/umami

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and DATABASE_URL are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
