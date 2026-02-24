# Matrix Synapse Dockerfile for Hop3
# Matrix homeserver implementation

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
DATA_DIR=/home/synapse/data\n\
\n\
# Generate homeserver.yaml if not exists\n\
if [ ! -f "$DATA_DIR/homeserver.yaml" ]; then\n\
    /home/synapse/venv/bin/python -m synapse.app.homeserver \\\n\
        --server-name "${SERVER_NAME:-localhost}" \\\n\
        --config-path "$DATA_DIR/homeserver.yaml" \\\n\
        --generate-config \\\n\
        --report-stats no \\\n\
        --data-directory "$DATA_DIR"\n\
fi\n\
\n\
# Override database configuration if DATABASE_URL is set\n\
if [ -n "$DATABASE_URL" ]; then\n\
    cat >> "$DATA_DIR/homeserver.yaml" << EOF\n\
\n\
database:\n\
  name: psycopg2\n\
  args:\n\
    cp_min: 5\n\
    cp_max: 10\n\
EOF\n\
fi\n\
\n\
# Set port\n\
sed -i "s/port: 8008/port: ${PORT:-8080}/" "$DATA_DIR/homeserver.yaml"\n\
\n\
# Start Synapse\n\
chown -R synapse:synapse "$DATA_DIR"\n\
exec su synapse -c "/home/synapse/venv/bin/python -m synapse.app.homeserver --config-path $DATA_DIR/homeserver.yaml"\n\
' > /usr/local/bin/start-synapse.sh \
    && chmod +x /usr/local/bin/start-synapse.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-synapse.sh"]
