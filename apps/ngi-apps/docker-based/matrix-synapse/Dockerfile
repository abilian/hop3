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
RUN printf '%s\n' '#!/bin/bash' \
    'set -e' \
    '' \
    '# Fail if required env vars are not set' \
    'if [ -z "$PORT" ]; then echo "ERROR: PORT not set" >&2; exit 1; fi' \
    'if [ -z "$PGHOST" ]; then echo "ERROR: PGHOST not set" >&2; exit 1; fi' \
    '' \
    'DATA_DIR=/home/synapse/data' \
    '' \
    '# Generate homeserver.yaml if not exists' \
    'if [ ! -f "$DATA_DIR/homeserver.yaml" ]; then' \
    '    /home/synapse/venv/bin/python -m synapse.app.homeserver \' \
    '        --server-name "${SERVER_NAME:-localhost}" \' \
    '        --config-path "$DATA_DIR/homeserver.yaml" \' \
    '        --generate-config \' \
    '        --report-stats no \' \
    '        --data-directory "$DATA_DIR"' \
    'fi' \
    '' \
    '# Override database configuration for PostgreSQL' \
    'cat > "$DATA_DIR/database.yaml" << EOFDB' \
    'database:' \
    '  name: psycopg2' \
    '  allow_unsafe_locale: true' \
    '  args:' \
    '    host: $PGHOST' \
    '    port: ${PGPORT:-5432}' \
    '    database: $PGDATABASE' \
    '    user: $PGUSER' \
    '    password: $PGPASSWORD' \
    '    cp_min: 5' \
    '    cp_max: 10' \
    'EOFDB' \
    '' \
    '# Set port and bind address in config (bind to 0.0.0.0 for Docker)' \
    'sed -i "s/port: 8008/port: $PORT/" "$DATA_DIR/homeserver.yaml"' \
    'sed -i "s/- ::1/- 0.0.0.0/" "$DATA_DIR/homeserver.yaml"' \
    'sed -i "/- 127.0.0.1/d" "$DATA_DIR/homeserver.yaml"' \
    '' \
    '# Start Synapse with both config files' \
    'chown -R synapse:synapse "$DATA_DIR"' \
    'exec su synapse -c "/home/synapse/venv/bin/python -m synapse.app.homeserver --config-path $DATA_DIR/homeserver.yaml --config-path $DATA_DIR/database.yaml"' \
    > /usr/local/bin/start-synapse.sh \
    && chmod +x /usr/local/bin/start-synapse.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-synapse.sh"]
