# Vikunja Dockerfile for Hop3
# Open source task/project management

FROM debian:trixie-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install Go and build dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Install pnpm for frontend build.
# Pin to pnpm@8: Debian Trixie ships a Node.js 20.x patch whose builtin
# module surface is older than what pnpm 10.x expects, producing
# ERR_UNKNOWN_BUILTIN_MODULE on first invocation. Same root cause as
# the etherpad Dockerfile fix; default pin for any frontend-building
# Trixie app until the installer ships a NodeSource-based Node toolchain.
RUN npm install -g pnpm@8

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
FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and PG* are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
