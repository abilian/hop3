# Mattermost Dockerfile for Hop3
# Open source collaboration platform

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
cd /opt/mattermost\n\
\n\
# Configure database from Hop3 env vars\n\
export MM_SQLSETTINGS_DRIVERNAME="postgres"\n\
export MM_SQLSETTINGS_DATASOURCE="${DATABASE_URL}"\n\
\n\
# Listen on PORT\n\
export MM_SERVICESETTINGS_LISTENADDRESS=":${PORT:-8080}"\n\
\n\
# Run as mattermost user\n\
exec su mattermost -c "cd /opt/mattermost && ./bin/mattermost"\n\
' > /usr/local/bin/start-mattermost.sh \
    && chmod +x /usr/local/bin/start-mattermost.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-mattermost.sh"]
