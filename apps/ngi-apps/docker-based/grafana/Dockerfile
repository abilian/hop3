# Grafana Dockerfile for Hop3
# The open observability platform

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    adduser \
    libfontconfig1 \
    musl \
    && rm -rf /var/lib/apt/lists/*

# Create grafana user
RUN adduser --system --uid 472 --group --home /var/lib/grafana grafana

# Create directories
RUN mkdir -p /var/lib/grafana /var/log/grafana /etc/grafana/provisioning \
    && chown -R grafana:grafana /var/lib/grafana /var/log/grafana /etc/grafana

WORKDIR /usr/share/grafana

# Download Grafana OSS
ARG GRAFANA_VERSION=11.0.0
RUN curl -fsSL "https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz" \
    -o /tmp/grafana.tar.gz \
    && tar -xzf /tmp/grafana.tar.gz --strip-components=1 -C /usr/share/grafana \
    && rm /tmp/grafana.tar.gz \
    && chown -R grafana:grafana /usr/share/grafana

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Grafana configuration\n\
export GF_SERVER_HTTP_PORT="${PORT:-8080}"\n\
export GF_PATHS_DATA="${GF_PATHS_DATA:-/var/lib/grafana}"\n\
export GF_PATHS_LOGS="${GF_PATHS_LOGS:-/var/log/grafana}"\n\
export GF_PATHS_PROVISIONING="${GF_PATHS_PROVISIONING:-/etc/grafana/provisioning}"\n\
export GF_SECURITY_ADMIN_USER="${GF_SECURITY_ADMIN_USER:-admin}"\n\
export GF_SECURITY_ADMIN_PASSWORD="${GF_SECURITY_ADMIN_PASSWORD:-admin}"\n\
\n\
# Ensure proper ownership\n\
chown -R grafana:grafana /var/lib/grafana /var/log/grafana\n\
\n\
# Run Grafana as grafana user\n\
exec su grafana -s /bin/bash -c "/usr/share/grafana/bin/grafana-server \\\n\
    --homepath=/usr/share/grafana \\\n\
    --config=/usr/share/grafana/conf/defaults.ini \\\n\
    cfg:default.paths.data=${GF_PATHS_DATA} \\\n\
    cfg:default.paths.logs=${GF_PATHS_LOGS} \\\n\
    cfg:default.paths.provisioning=${GF_PATHS_PROVISIONING}"\n\
' > /usr/local/bin/start-grafana.sh \
    && chmod +x /usr/local/bin/start-grafana.sh

# Environment
ENV PORT=8080
ENV GF_PATHS_DATA=/var/lib/grafana
ENV GF_PATHS_LOGS=/var/log/grafana

# Data volume
VOLUME /var/lib/grafana

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-grafana.sh"]
