# Wiki.js Dockerfile for Hop3
# Modern wiki software

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js
RUN apt-get update -q && apt-get install -q -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create wiki user
RUN useradd -m -s /bin/bash wiki

WORKDIR /home/wiki/app

# Download Wiki.js release (prebuilt)
ARG WIKIJS_VERSION=2.5.303
RUN curl -sL "https://github.com/Requarks/wiki/releases/download/v${WIKIJS_VERSION}/wiki-js.tar.gz" | tar xz \
    && chown -R wiki:wiki /home/wiki

# Copy startup script
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Environment (PORT is required, no default)
EXPOSE 8080

CMD ["/usr/local/bin/start.sh"]
