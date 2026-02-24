# Formbricks Dockerfile for Hop3
# Open source survey and experience management

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create formbricks user (home at /home/formbricks, not /app)
RUN useradd -m -s /bin/bash formbricks

# Create directories
RUN mkdir -p /app /data \
    && chown -R formbricks:formbricks /app /data

WORKDIR /app

# Download and build Formbricks
ARG FORMBRICKS_VERSION=v2.6.0
RUN git clone --depth 1 --branch ${FORMBRICKS_VERSION} https://github.com/formbricks/formbricks.git /app \
    && chown -R formbricks:formbricks /app

# Install dependencies and build as formbricks user
USER formbricks
RUN npm install --legacy-peer-deps \
    && npm run build --filter=@formbricks/web

USER root

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Database configuration (Hop3 injects PG* vars)\n\
export PGHOST="${PGHOST:-localhost}"\n\
export PGPORT="${PGPORT:-5432}"\n\
export PGDATABASE="${PGDATABASE:-formbricks}"\n\
export PGUSER="${PGUSER:-formbricks}"\n\
export PGPASSWORD="${PGPASSWORD:-}"\n\
\n\
# Formbricks configuration\n\
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT}/${PGDATABASE}"\n\
export PORT="${PORT:-8080}"\n\
export NEXTAUTH_URL="${NEXTAUTH_URL:-http://localhost:${PORT}}"\n\
export NEXTAUTH_SECRET="${NEXTAUTH_SECRET:-$(head -c 32 /dev/urandom | base64)}"\n\
export ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(head -c 24 /dev/urandom | base64 | tr -dc a-zA-Z0-9 | head -c 32)}"\n\
\n\
# Run database migrations\n\
cd /app/apps/web\n\
npx prisma migrate deploy || true\n\
\n\
# Run Formbricks\n\
exec su formbricks -c "cd /app/apps/web && npm start"\n\
' > /usr/local/bin/start-formbricks.sh \
    && chmod +x /usr/local/bin/start-formbricks.sh

# Environment
ENV PORT=8080
ENV NODE_ENV=production

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-formbricks.sh"]
