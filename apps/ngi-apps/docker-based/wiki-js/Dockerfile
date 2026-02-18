# Wiki.js Dockerfile for Hop3
# Modern wiki software

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js 18 LTS
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create wiki user
RUN useradd -m -s /bin/bash wiki

WORKDIR /home/wiki/app

# Download Wiki.js release (prebuilt)
ARG WIKIJS_VERSION=2.5.303
RUN curl -sL "https://github.com/Requarks/wiki/releases/download/v${WIKIJS_VERSION}/wiki-js.tar.gz" | tar xz \
    && chown -R wiki:wiki /home/wiki

# Create startup script that generates config.yml
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/wiki/app\n\
\n\
# Generate config.yml from environment variables\n\
cat > config.yml << EOF\n\
port: ${PORT:-8080}\n\
db:\n\
  type: postgres\n\
  host: ${PGHOST:-localhost}\n\
  port: ${PGPORT:-5432}\n\
  user: ${PGUSER:-wiki}\n\
  pass: ${PGPASSWORD}\n\
  db: ${PGDATABASE:-wiki}\n\
bindIP: 0.0.0.0\n\
logLevel: info\n\
EOF\n\
\n\
chown wiki:wiki config.yml\n\
\n\
# Run as wiki user\n\
exec su wiki -c "cd /home/wiki/app && node server"\n\
' > /usr/local/bin/start-wiki.sh \
    && chmod +x /usr/local/bin/start-wiki.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-wiki.sh"]
