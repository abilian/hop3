# Demo 25: Filebrowser
# A web-based file browser (no database required)

FROM debian:bookworm-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates python3 && \
    rm -rf /var/lib/apt/lists/*

# renovate: datasource=github-releases depName=filebrowser/filebrowser
ARG FILEBROWSER_VERSION=2.31.2
ARG TARGETARCH

# Download and extract Filebrowser (architecture-aware)
RUN ARCH=$(case ${TARGETARCH:-$(dpkg --print-architecture)} in \
        amd64) echo "amd64" ;; \
        arm64) echo "arm64" ;; \
        armhf|arm) echo "armv7" ;; \
        *) echo "amd64" ;; \
    esac) && \
    echo "==> Downloading Filebrowser for architecture: ${ARCH}" && \
    curl -fsSL "https://github.com/filebrowser/filebrowser/releases/download/v${FILEBROWSER_VERSION}/linux-${ARCH}-filebrowser.tar.gz" | tar xzf - -C /app

# Create data directories
RUN mkdir -p /srv /app/database

COPY start.py /app/start.py

EXPOSE 8080

CMD ["python3", "/app/start.py"]
