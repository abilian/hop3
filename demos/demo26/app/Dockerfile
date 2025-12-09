# Demo 26: Miniflux
# A minimalist RSS reader with PostgreSQL

FROM debian:bookworm-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates python3 && \
    rm -rf /var/lib/apt/lists/*

# renovate: datasource=github-releases depName=miniflux/v2
ARG MINIFLUX_VERSION=2.2.14
ARG TARGETARCH

# Download Miniflux binary (architecture-aware)
RUN ARCH=$(case ${TARGETARCH:-$(dpkg --print-architecture)} in \
        amd64) echo "amd64" ;; \
        arm64) echo "arm64" ;; \
        armhf|arm) echo "armv7" ;; \
        *) echo "amd64" ;; \
    esac) && \
    echo "==> Downloading Miniflux for architecture: ${ARCH}" && \
    curl -fsSL "https://github.com/miniflux/v2/releases/download/${MINIFLUX_VERSION}/miniflux-linux-${ARCH}" -o /app/miniflux && \
    chmod +x /app/miniflux

COPY start.py /app/start.py

EXPOSE 8080

CMD ["python3", "/app/start.py"]
