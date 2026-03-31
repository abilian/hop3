# Matrix Synapse Dockerfile for Hop3
# Matrix homeserver implementation

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    libjpeg-dev \
    libxml2-dev \
    libxslt1-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create synapse user
RUN useradd -m -s /bin/bash synapse

WORKDIR /home/synapse

# Create virtual environment and install Synapse
ARG SYNAPSE_VERSION=1.147.1
RUN python3 -m venv /home/synapse/venv \
    && /home/synapse/venv/bin/pip install --upgrade pip \
    && /home/synapse/venv/bin/pip install "matrix-synapse[postgres,redis]==${SYNAPSE_VERSION}"

# Create data directory
RUN mkdir -p /home/synapse/data \
    && chown -R synapse:synapse /home/synapse

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
