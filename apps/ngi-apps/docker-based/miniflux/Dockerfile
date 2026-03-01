# Miniflux Dockerfile for Hop3
# Minimalist RSS reader

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create miniflux user
RUN useradd -m -s /bin/bash miniflux

# Download Miniflux binary
ARG MINIFLUX_VERSION=2.1.1
RUN curl -sL "https://github.com/miniflux/v2/releases/download/${MINIFLUX_VERSION}/miniflux-linux-amd64" -o /usr/local/bin/miniflux \
    && chmod +x /usr/local/bin/miniflux

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Miniflux uses DATABASE_URL directly from environment\n\
export LISTEN_ADDR="0.0.0.0:${PORT:-8080}"\n\
\n\
exec /usr/local/bin/miniflux\n\
' > /usr/local/bin/start-miniflux.sh \
    && chmod +x /usr/local/bin/start-miniflux.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-miniflux.sh"]
