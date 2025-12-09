# Demo 25: OpenCloud
# A modern file sharing and collaboration platform (no database required)

FROM debian:bookworm-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates attr && \
    rm -rf /var/lib/apt/lists/*

# Download OpenCloud binary
# renovate: datasource=github-releases depName=opencloud-eu/opencloud versioning=semver
ARG OPENCLOUD_VERSION=4.0.0
RUN curl -L https://github.com/opencloud-eu/opencloud/releases/download/v${OPENCLOUD_VERSION}/opencloud-${OPENCLOUD_VERSION}-linux-amd64 > /app/opencloud && \
    chmod +x /app/opencloud

# Set up directories
RUN mkdir -p /app/data/config /app/data/data

# Environment variables for data paths
ENV OC_CONFIG_DIR=/app/data/config
ENV OC_BASE_DATA_PATH=/app/data/data

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 9200

CMD ["/app/start.sh"]
