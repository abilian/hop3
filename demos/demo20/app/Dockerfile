# Demo 20: Umami Analytics
# Self-hosted web analytics
# Using Debian-based image for OpenSSL compatibility with Prisma

FROM node:22-slim

WORKDIR /app

# renovate: datasource=github-releases depName=umami-software/umami
ARG UMAMI_VERSION=2.15.1

# Install dependencies including OpenSSL for Prisma
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

# Download and extract Umami
RUN curl -L https://github.com/umami-software/umami/archive/refs/tags/v${UMAMI_VERSION}.tar.gz | tar zxvf - --strip-components 1

# Install yarn and dependencies
RUN corepack enable && yarn install

# Build for PostgreSQL
# Skip database check during build (database not available)
# The actual DATABASE_URL is provided at runtime
ENV DATABASE_TYPE=postgresql
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_URL=postgresql://build:build@localhost:5432/build
ENV SKIP_DB_CHECK=1
RUN yarn build

# Copy static files for standalone mode
# Next.js standalone doesn't include static files, they must be copied manually
RUN cp -r .next/static .next/standalone/.next/static && \
    cp -r public .next/standalone/public

# Expose port
EXPOSE 3000

# Start script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
