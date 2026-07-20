# Linkding Bookmark Manager for Hop3
# Self-hosted bookmark manager
# https://github.com/sissbruecker/linkding
# Built from source on debian:bookworm-slim

FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# Linkding version (v1.23.1 is compatible with Python 3.11 in bookworm)
ARG LINKDING_VERSION=v1.23.1

# Create app directory and user
RUN useradd -m -d /app -s /bin/bash -u 1000 linkding

WORKDIR /app

# Download and extract Linkding
RUN curl -fsSL "https://github.com/sissbruecker/linkding/archive/refs/tags/${LINKDING_VERSION}.tar.gz" | \
    tar -xz --strip-components=1

# Create virtual environment and install Python dependencies
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    /app/venv/bin/pip install --no-cache-dir psycopg2-binary gunicorn

# Build frontend assets
RUN npm install && npm run build

# Set permissions
RUN mkdir -p /app/data && \
    chown -R linkding:linkding /app

# Copy startup script
COPY --chmod=755 start.sh /start.sh

# Runtime environment
ENV PATH="/app/venv/bin:$PATH" \
    LD_LIBRARY_PATH=/app/venv/lib \
    LD_DATA_DIR=/app/data \
    LD_SERVER_PORT=9090

EXPOSE 9090

USER linkding

CMD ["/start.sh"]
