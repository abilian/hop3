# Demo 54: Miniflux RSS Reader
# Minimalist and opinionated feed reader
# https://miniflux.app/
# Built on debian:bookworm-slim with pre-built binary

FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Miniflux version
ARG MINIFLUX_VERSION=2.2.15

# Download and install Miniflux binary
WORKDIR /app
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then MINIFLUX_ARCH="amd64"; \
    elif [ "$ARCH" = "arm64" ]; then MINIFLUX_ARCH="arm64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    curl -fsSL "https://github.com/miniflux/v2/releases/download/${MINIFLUX_VERSION}/miniflux-linux-${MINIFLUX_ARCH}" -o miniflux && \
    chmod +x miniflux

# Create non-root user
RUN useradd -m -d /app -s /bin/bash -u 1000 miniflux && \
    chown -R miniflux:miniflux /app

# Copy startup script
COPY --chmod=755 start.sh /start.sh

# Runtime environment
ENV LISTEN_ADDR=0.0.0.0:8080 \
    RUN_MIGRATIONS=1

EXPOSE 8080

USER miniflux

CMD ["/start.sh"]
