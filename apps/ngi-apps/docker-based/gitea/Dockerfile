# Gitea Dockerfile for Hop3
# Self-hosted Git service

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies including envsubst
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    curl \
    ca-certificates \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Create gitea user
RUN useradd -m -s /bin/bash gitea

# Create app directory
WORKDIR /home/gitea

# Download Gitea binary
ARG GITEA_VERSION=1.21.5
ARG TARGETARCH=amd64
RUN curl -sL "https://dl.gitea.com/gitea/${GITEA_VERSION}/gitea-${GITEA_VERSION}-linux-${TARGETARCH}" -o /usr/local/bin/gitea \
    && chmod +x /usr/local/bin/gitea

# Create required directories
RUN mkdir -p /home/gitea/custom/conf /home/gitea/data /home/gitea/repos /home/gitea/log \
    && chown -R gitea:gitea /home/gitea

# Copy config template
COPY --chown=gitea:gitea app.ini.template /home/gitea/custom/conf/app.ini.template

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Set defaults for config vars (Hop3 injects PG* vars)\n\
export PGHOST="${PGHOST:-localhost}"\n\
export PGPORT="${PGPORT:-5432}"\n\
export PGDATABASE="${PGDATABASE:-gitea}"\n\
export PGUSER="${PGUSER:-gitea}"\n\
export PGPASSWORD="${PGPASSWORD:-}"\n\
\n\
# Gitea config defaults\n\
export GITEA_APP_NAME="${GITEA_APP_NAME:-Gitea: Git with a cup of tea}"\n\
export GITEA_RUN_MODE="${GITEA_RUN_MODE:-prod}"\n\
export GITEA_REPO_ROOT="${GITEA_REPO_ROOT:-./repos}"\n\
export GITEA_DOMAIN="${GITEA_DOMAIN:-localhost}"\n\
export GITEA_HTTP_PORT="${PORT:-8080}"\n\
export GITEA_ROOT_URL="${GITEA_ROOT_URL:-http://localhost:${GITEA_HTTP_PORT}/}"\n\
export GITEA_LOG_LEVEL="${GITEA__log__LEVEL:-Info}"\n\
\n\
# Generate secrets if not provided\n\
export GITEA_SECRET_KEY="${GITEA_SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"\n\
export GITEA_INTERNAL_TOKEN="${GITEA_INTERNAL_TOKEN:-$(head -c 64 /dev/urandom | base64)}"\n\
\n\
# Substitute environment variables in config\n\
envsubst < /home/gitea/custom/conf/app.ini.template > /home/gitea/custom/conf/app.ini\n\
chown gitea:gitea /home/gitea/custom/conf/app.ini\n\
\n\
# Run Gitea as gitea user\n\
exec su gitea -c "cd /home/gitea && /usr/local/bin/gitea web --config /home/gitea/custom/conf/app.ini"\n\
' > /usr/local/bin/start-gitea.sh \
    && chmod +x /usr/local/bin/start-gitea.sh

# Environment (Hop3 uses 8080 as standard container port)
ENV GITEA_WORK_DIR=/home/gitea
ENV GITEA_CUSTOM=/home/gitea/custom
ENV PORT=8080

EXPOSE 8080

USER root
CMD ["/usr/local/bin/start-gitea.sh"]
