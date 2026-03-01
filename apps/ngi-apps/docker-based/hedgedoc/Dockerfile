# HedgeDoc Dockerfile for Hop3
# Real-time collaborative markdown editor

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js with Corepack (for Yarn Berry)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    curl \
    ca-certificates \
    && corepack enable \
    && rm -rf /var/lib/apt/lists/*

# Create hedgedoc user
RUN useradd -m -s /bin/bash hedgedoc

# Create app directory
WORKDIR /home/hedgedoc/app

# Download and build HedgeDoc
ARG HEDGEDOC_VERSION=1.10.6
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV YARN_CACHE_FOLDER=/tmp/.yarn
RUN curl -sL "https://github.com/hedgedoc/hedgedoc/archive/refs/tags/${HEDGEDOC_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && yarn install --immutable \
    && yarn run build \
    && yarn workspaces focus --production \
    && chown -R hedgedoc:hedgedoc /home/hedgedoc

# Copy configuration template
COPY --chown=hedgedoc:hedgedoc config.json.template config.json

# Create uploads directory
RUN mkdir -p /home/hedgedoc/app/public/uploads \
    && chown -R hedgedoc:hedgedoc /home/hedgedoc/app/public/uploads

# Environment variables (Hop3 uses 8080 as standard container port)
ENV CMD_DOMAIN=localhost
ENV CMD_URL_ADDPORT=false
ENV CMD_PROTOCOL_USESSL=false
ENV CMD_ALLOW_ANONYMOUS=true
ENV CMD_ALLOW_ANONYMOUS_EDITS=true
ENV CMD_IMAGE_UPLOAD_TYPE=filesystem
ENV CMD_UPLOADS_PATH=./public/uploads
ENV PORT=8080

# Create startup script to map Hop3 env vars to HedgeDoc env vars
USER root
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Set HedgeDoc port from Hop3 PORT\n\
export CMD_PORT="${PORT:-8080}"\n\
\n\
# Map Hop3 DATABASE_URL to HedgeDoc CMD_DB_URL\n\
if [ -n "$DATABASE_URL" ]; then\n\
  export CMD_DB_URL="$DATABASE_URL"\n\
fi\n\
\n\
# Map individual PG* variables if DATABASE_URL not set\n\
if [ -z "$CMD_DB_URL" ] && [ -n "$PGHOST" ]; then\n\
  export CMD_DB_URL="postgres://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT:-5432}/${PGDATABASE}"\n\
fi\n\
\n\
cd /home/hedgedoc/app\n\
exec su hedgedoc -c "cd /home/hedgedoc/app && CMD_PORT=${CMD_PORT} CMD_DB_URL=${CMD_DB_URL} node app.js"\n\
' > /usr/local/bin/start-hedgedoc.sh \
    && chmod +x /usr/local/bin/start-hedgedoc.sh

EXPOSE 8080

CMD ["/usr/local/bin/start-hedgedoc.sh"]
