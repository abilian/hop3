# Umami Dockerfile for Hop3
# Privacy-focused web analytics

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js 18 LTS and build tools for native modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    python3 \
    make \
    g++ \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -s /bin/bash umami

WORKDIR /home/umami/app

# Download and build Umami
# Umami requires DATABASE_URL at build time for Prisma
# Skip check-db step (requires actual DB connection) and run build steps individually
ARG UMAMI_VERSION=v2.10.1
ENV DATABASE_URL="postgresql://build:build@localhost:5432/build"
# Need devDependencies for build (rollup), so temporarily unset NODE_ENV
# Use --ignore-scripts to skip broken native module builds (optional deps)
RUN curl -sL "https://github.com/umami-software/umami/archive/refs/tags/${UMAMI_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && NODE_ENV=development npm install --legacy-peer-deps --ignore-scripts \
    && npm run build-db \
    && npm run build-tracker \
    && npm run build-app \
    && npm prune --production --legacy-peer-deps \
    && chown -R umami:umami /home/umami

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/umami/app\n\
\n\
# Umami uses DATABASE_URL directly\n\
exec su umami -c "cd /home/umami/app && npm start"\n\
' > /usr/local/bin/start-umami.sh \
    && chmod +x /usr/local/bin/start-umami.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-umami.sh"]
