# Focalboard Dockerfile for Hop3
# Open source project management

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create focalboard user
RUN useradd -m -s /bin/bash focalboard

WORKDIR /opt/focalboard

# Download Focalboard (moved to mattermost-community)
ARG FOCALBOARD_VERSION=7.10.5
RUN curl -sL "https://github.com/mattermost-community/focalboard/releases/download/v${FOCALBOARD_VERSION}/focalboard-server-linux-amd64.tar.gz" | tar xz --strip-components=1 \
    && chown -R focalboard:focalboard /opt/focalboard

# Create config file
RUN echo '#!/bin/bash\n\
set -e\n\
cd /opt/focalboard\n\
\n\
# Create config from environment\n\
cat > config.json << EOF\n\
{\n\
  "serverRoot": "http://localhost:${PORT:-8080}",\n\
  "port": ${PORT:-8080},\n\
  "dbtype": "postgres",\n\
  "dbconfig": "${DATABASE_URL}",\n\
  "useSSL": false,\n\
  "webpath": "./pack",\n\
  "filespath": "./files",\n\
  "telemetry": false,\n\
  "session_expire_time": 2592000,\n\
  "session_refresh_time": 18000,\n\
  "localOnly": false,\n\
  "enableLocalMode": true,\n\
  "localModeSocketLocation": "/var/tmp/focalboard_local.socket"\n\
}\n\
EOF\n\
\n\
exec ./bin/focalboard-server\n\
' > /usr/local/bin/start-focalboard.sh \
    && chmod +x /usr/local/bin/start-focalboard.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-focalboard.sh"]
