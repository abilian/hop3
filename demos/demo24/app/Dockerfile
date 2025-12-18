# Demo 24: Listmonk
# A high-performance newsletter and mailing list manager with PostgreSQL
# Built from official binary on debian:bookworm-slim

FROM debian:bookworm-slim

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Listmonk version
ARG LISTMONK_VERSION=5.1.0

WORKDIR /app

# Download and extract Listmonk binary based on architecture
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        LISTMONK_ARCH="amd64"; \
    elif [ "$ARCH" = "arm64" ]; then \
        LISTMONK_ARCH="arm64"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    curl -fsSL "https://github.com/knadh/listmonk/releases/download/v${LISTMONK_VERSION}/listmonk_${LISTMONK_VERSION}_linux_${LISTMONK_ARCH}.tar.gz" | \
    tar -xz && \
    chmod +x listmonk

# Copy startup script
COPY start.py /app/start.py

EXPOSE 9000

CMD ["python3", "/app/start.py"]
