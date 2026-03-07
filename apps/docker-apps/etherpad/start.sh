#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

cd /home/etherpad/app

# Create settings.json with correct port
cat > settings.json << SETTINGS
{
  "title": "Etherpad",
  "favicon": "favicon.ico",
  "skinName": "colibris",
  "skinVariants": "super-light-toolbar super-light-editor light-background",
  "ip": "0.0.0.0",
  "port": ${PORT},
  "showSettingsInAdminPage": true,
  "dbType": "dirty",
  "dbSettings": {
    "filename": "var/dirty.db"
  },
  "defaultPadText": "Welcome to Etherpad!",
  "padOptions": {
    "noColors": false,
    "showControls": true,
    "showChat": true,
    "showLineNumbers": true,
    "useMonospaceFont": false,
    "userName": false,
    "userColor": false,
    "rtl": false,
    "alwaysShowChat": false,
    "chatAndUsers": false,
    "lang": "en-gb"
  },
  "suppressErrorsInPadText": false,
  "requireSession": false,
  "editOnly": false,
  "minify": true,
  "maxAge": 21600,
  "abiword": null,
  "soffice": null,
  "tidyHtml": null,
  "allowUnknownFileEnds": true,
  "requireAuthentication": false,
  "requireAuthorization": false,
  "trustProxy": true,
  "disableIPlogging": false,
  "automaticReconnectionTimeout": 0,
  "scrollWhenFocusLineIsOutOfViewport": {
    "percentage": {
      "editionAboveViewport": 0,
      "editionBelowViewport": 0
    },
    "duration": 0,
    "scrollWhenCaretIsInTheLastLineOfViewport": false,
    "percentageToScrollWhenUserPressesArrowUp": 0
  },
  "socketTransportProtocols": ["websocket", "polling"],
  "socketIo": {
    "maxHttpBufferSize": 50000
  },
  "loadTest": false,
  "dumpOnUncleanExit": false,
  "exposeVersion": false,
  "loglevel": "INFO",
  "logconfig": {
    "appenders": {
      "console": {
        "type": "console"
      }
    },
    "categories": {
      "default": {
        "appenders": ["console"],
        "level": "INFO"
      }
    }
  }
}
SETTINGS
chown etherpad:etherpad settings.json

# Create var directory for dirty.db
mkdir -p var
chown etherpad:etherpad var

# Run etherpad from src directory (where server.ts is)
exec su etherpad -c "cd /home/etherpad/app/src && ../node_modules/.pnpm/node_modules/.bin/tsx node/server.ts"
