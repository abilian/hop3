# Focalboard Dockerfile for Hop3
# Open source project management

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
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

# Copy startup script
COPY start-focalboard.sh /usr/local/bin/start-focalboard.sh
RUN chmod +x /usr/local/bin/start-focalboard.sh

# Environment (PORT and DATABASE_URL are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start-focalboard.sh"]
