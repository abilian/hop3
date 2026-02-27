# Vikunja Dockerfile for Hop3
# Open source task/project management

FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install Go and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    build-essential \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Go (detect architecture)
ARG GO_VERSION=1.22.0
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" | tar xz -C /usr/local
ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOPATH="/go"
ENV PATH="${GOPATH}/bin:${PATH}"

# Install pnpm for frontend build
RUN npm install -g pnpm

WORKDIR /build

# Download and build Vikunja from source
ARG VIKUNJA_VERSION=0.24.6
RUN curl -sL "https://github.com/go-vikunja/vikunja/archive/refs/tags/v${VIKUNJA_VERSION}.tar.gz" | tar xz --strip-components=1

# Build frontend (skip puppeteer browser download)
ENV PUPPETEER_SKIP_DOWNLOAD=true
RUN cd frontend && pnpm install && pnpm run build

# Build backend (main package is at root in v0.22+)
RUN go build -o vikunja .

# Runtime image
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Create vikunja user
RUN useradd -m -s /bin/bash vikunja

WORKDIR /app

# Copy binary and frontend from builder
COPY --from=builder /build/vikunja /app/vikunja
COPY --from=builder /build/frontend/dist /app/frontend/dist

# Create directories
RUN mkdir -p /app/files /app/db \
    && chown -R vikunja:vikunja /app

# Create startup script
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    '# Fail if required env vars are not set' \
    'if [ -z "$PORT" ]; then echo "ERROR: PORT not set" >&2; exit 1; fi' \
    'if [ -z "$PGHOST" ]; then echo "ERROR: PGHOST not set" >&2; exit 1; fi' \
    '' \
    '# Vikunja uses env vars directly with VIKUNJA_ prefix' \
    'export VIKUNJA_SERVICE_INTERFACE=":$PORT"' \
    'export VIKUNJA_SERVICE_FRONTENDURL="${VIKUNJA_FRONTEND_URL:-http://localhost:$PORT/}"' \
    'export VIKUNJA_DATABASE_TYPE="postgres"' \
    'export VIKUNJA_DATABASE_HOST="$PGHOST"' \
    'export VIKUNJA_DATABASE_PORT="${PGPORT:-5432}"' \
    'export VIKUNJA_DATABASE_DATABASE="$PGDATABASE"' \
    'export VIKUNJA_DATABASE_USER="$PGUSER"' \
    'export VIKUNJA_DATABASE_PASSWORD="$PGPASSWORD"' \
    'export VIKUNJA_FILES_BASEPATH="/app/files"' \
    'export VIKUNJA_MAILER_ENABLED="false"' \
    'export VIKUNJA_LOG_LEVEL="info"' \
    '' \
    'chown -R vikunja:vikunja /app' \
    '' \
    '# Start Vikunja' \
    'exec su vikunja -c "/app/vikunja"' \
    > /usr/local/bin/start-vikunja.sh \
    && chmod +x /usr/local/bin/start-vikunja.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-vikunja.sh"]
