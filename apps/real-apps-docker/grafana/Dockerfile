# Grafana Dockerfile for Hop3
# The open observability platform

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
ENV GF_PATHS_DATA=/var/lib/grafana
ENV GF_PATHS_LOGS=/var/log/grafana

# Data volume
VOLUME /var/lib/grafana

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start.sh"]
