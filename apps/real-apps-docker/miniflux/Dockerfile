# Miniflux Dockerfile for Hop3
# Minimalist RSS reader

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create miniflux user
RUN useradd -m -s /bin/bash miniflux

# Download Miniflux binary
ARG MINIFLUX_VERSION=2.1.1
RUN curl -sL "https://github.com/miniflux/v2/releases/download/${MINIFLUX_VERSION}/miniflux-linux-amd64" -o /usr/local/bin/miniflux \
    && chmod +x /usr/local/bin/miniflux

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT and DATABASE_URL are required, no defaults)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
