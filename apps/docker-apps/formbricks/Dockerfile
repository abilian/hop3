# Formbricks Dockerfile for Hop3
# Open source survey and experience management

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Node.js and dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    git \
    && corepack enable \
    && corepack prepare pnpm@latest --activate \
    && rm -rf /var/lib/apt/lists/*

# Create formbricks user (home at /home/formbricks, not /app)
RUN useradd -m -s /bin/bash formbricks

# Create directories
RUN mkdir -p /app /data \
    && chown -R formbricks:formbricks /app /data

WORKDIR /app

# Download and build Formbricks
ARG FORMBRICKS_VERSION=v2.6.0
RUN git clone --depth 1 --branch ${FORMBRICKS_VERSION} https://github.com/formbricks/formbricks.git /app \
    && chown -R formbricks:formbricks /app

# Install dependencies and build as formbricks user
# Note: Formbricks uses @t3-oss/env which validates env vars at build time
USER formbricks

# Create .env file FIRST (required before install and build)
RUN echo "CRON_SECRET=build_placeholder_secret" > /app/apps/web/.env \
    && echo "DATABASE_URL=postgresql://build:build@localhost:5432/build" >> /app/apps/web/.env \
    && echo "ENCRYPTION_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" >> /app/apps/web/.env \
    && echo "NEXTAUTH_SECRET=build_placeholder_nextauth_secret" >> /app/apps/web/.env \
    && echo "NEXTAUTH_URL=http://localhost:8080" >> /app/apps/web/.env

# Install and build (increase heap for large Next.js build)
RUN pnpm install \
    && NODE_OPTIONS="--max-old-space-size=4096" pnpm build --filter=@formbricks/web \
    && test -f /app/apps/web/.next/BUILD_ID || (echo "ERROR: Build failed - no BUILD_ID" && exit 1)

USER root

# Copy startup script
COPY start-formbricks.sh /usr/local/bin/start-formbricks.sh
RUN chmod +x /usr/local/bin/start-formbricks.sh

# Environment (PORT and database vars are required, no defaults)
ENV NODE_ENV=production

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-formbricks.sh"]
