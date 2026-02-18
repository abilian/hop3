# Etherpad Dockerfile for Hop3
# Real-time collaborative editor

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production

# Install Node.js 18 LTS and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    python3 \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create etherpad user
RUN useradd -m -s /bin/bash etherpad

WORKDIR /home/etherpad/app

# Download Etherpad and install dependencies
ARG ETHERPAD_VERSION=2.0.3
ENV CI=true
RUN curl -sL "https://github.com/ether/etherpad-lite/archive/refs/tags/v${ETHERPAD_VERSION}.tar.gz" | tar xz --strip-components=1 \
    && bin/installDeps.sh \
    && chown -R etherpad:etherpad /home/etherpad

# Create startup script that runs node directly (skip bin/run.sh which reinstalls deps)
RUN echo '#!/bin/bash\n\
set -e\n\
cd /home/etherpad/app\n\
\n\
# Always create settings.json with correct port (ignore template which uses 9001)\n\
cat > settings.json << SETTINGS\n\
{\n\
  "title": "Etherpad",\n\
  "favicon": "favicon.ico",\n\
  "skinName": "colibris",\n\
  "skinVariants": "super-light-toolbar super-light-editor light-background",\n\
  "ip": "0.0.0.0",\n\
  "port": 8080,\n\
  "showSettingsInAdminPage": true,\n\
  "dbType": "dirty",\n\
  "dbSettings": {\n\
    "filename": "var/dirty.db"\n\
  },\n\
  "defaultPadText": "Welcome to Etherpad!",\n\
  "padOptions": {\n\
    "noColors": false,\n\
    "showControls": true,\n\
    "showChat": true,\n\
    "showLineNumbers": true,\n\
    "useMonospaceFont": false,\n\
    "userName": false,\n\
    "userColor": false,\n\
    "rtl": false,\n\
    "alwaysShowChat": false,\n\
    "chatAndUsers": false,\n\
    "lang": "en-gb"\n\
  },\n\
  "suppressErrorsInPadText": false,\n\
  "requireSession": false,\n\
  "editOnly": false,\n\
  "minify": true,\n\
  "maxAge": 21600,\n\
  "abiword": null,\n\
  "soffice": null,\n\
  "tidyHtml": null,\n\
  "allowUnknownFileEnds": true,\n\
  "requireAuthentication": false,\n\
  "requireAuthorization": false,\n\
  "trustProxy": true,\n\
  "disableIPlogging": false,\n\
  "automaticReconnectionTimeout": 0,\n\
  "scrollWhenFocusLineIsOutOfViewport": {\n\
    "percentage": {\n\
      "editionAboveViewport": 0,\n\
      "editionBelowViewport": 0\n\
    },\n\
    "duration": 0,\n\
    "scrollWhenCaretIsInTheLastLineOfViewport": false,\n\
    "percentageToScrollWhenUserPressesArrowUp": 0\n\
  },\n\
  "socketTransportProtocols": ["websocket", "polling"],\n\
  "socketIo": {\n\
    "maxHttpBufferSize": 50000\n\
  },\n\
  "loadTest": false,\n\
  "dumpOnUncleanExit": false,\n\
  "exposeVersion": false,\n\
  "loglevel": "INFO",\n\
  "logconfig": {\n\
    "appenders": {\n\
      "console": {\n\
        "type": "console"\n\
      }\n\
    },\n\
    "categories": {\n\
      "default": {\n\
        "appenders": ["console"],\n\
        "level": "INFO"\n\
      }\n\
    }\n\
  }\n\
}\n\
SETTINGS\n\
chown etherpad:etherpad settings.json\n\
\n\
# Create var directory for dirty.db\n\
mkdir -p var\n\
chown etherpad:etherpad var\n\
\n\
# Run etherpad from src directory (where server.ts is)\n\
exec su etherpad -c "cd /home/etherpad/app/src && ../node_modules/.pnpm/node_modules/.bin/tsx node/server.ts"\n\
' > /usr/local/bin/start-etherpad.sh \
    && chmod +x /usr/local/bin/start-etherpad.sh

ENV PORT=8080
EXPOSE 8080

CMD ["/usr/local/bin/start-etherpad.sh"]
