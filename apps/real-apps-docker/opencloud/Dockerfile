# OpenCloud Dockerfile for Hop3
# A self-hosted file sharing platform (Nextcloud alternative)

FROM debian:bookworm-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates attr python3 && \
    rm -rf /var/lib/apt/lists/*

# renovate: datasource=github-releases depName=opencloud-eu/opencloud
ARG OPENCLOUD_VERSION=4.0.0
ARG TARGETARCH

# Download OpenCloud binary (architecture-aware)
RUN ARCH=$(case ${TARGETARCH:-$(dpkg --print-architecture)} in \
        amd64) echo "amd64" ;; \
        arm64) echo "arm64" ;; \
        *) echo "amd64" ;; \
    esac) && \
    echo "==> Downloading OpenCloud for architecture: ${ARCH}" && \
    curl -fsSL "https://github.com/opencloud-eu/opencloud/releases/download/v${OPENCLOUD_VERSION}/opencloud-${OPENCLOUD_VERSION}-linux-${ARCH}" -o /app/opencloud && \
    chmod +x /app/opencloud

# Create data directories
RUN mkdir -p /app/data /app/config

ENV OC_CONFIG_DIR=/app/config
ENV OC_BASE_DATA_PATH=/app/data

COPY start.py /app/start.py

EXPOSE 9200

CMD ["python3", "/app/start.py"]
