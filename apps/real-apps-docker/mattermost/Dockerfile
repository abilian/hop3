# Mattermost Dockerfile for Hop3
# Open source collaboration platform

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create mattermost user
RUN useradd -m -s /bin/bash mattermost

WORKDIR /opt/mattermost

# Download and extract Mattermost
ARG MM_VERSION=9.5.2
RUN curl -sL "https://releases.mattermost.com/${MM_VERSION}/mattermost-${MM_VERSION}-linux-amd64.tar.gz" | tar xz --strip-components=1 \
    && mkdir -p data logs config plugins client/plugins \
    && chown -R mattermost:mattermost /opt/mattermost

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and DATABASE_URL are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
