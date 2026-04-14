# Directus Dockerfile for Hop3
# Built from debian:trixie-slim + Node.js + npm install directus

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22 (LTS) from NodeSource.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -q -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash directus

WORKDIR /opt/directus

ARG DIRECTUS_VERSION=11.17.2
RUN npm init -y \
    && npm install --no-audit --no-fund --loglevel=error \
        "directus@${DIRECTUS_VERSION}" \
        "pg@^8.11.0"

RUN mkdir -p /data && chown -R directus:directus /opt/directus /data

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

EXPOSE 8055

CMD ["/usr/local/bin/start.sh"]
