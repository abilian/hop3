#!/bin/bash
# Setup Etherpad settings from environment variables

set -e

PORT="${PORT:-8080}"

# Create var directory for dirty.db
mkdir -p var

cat > settings.json << EOF
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
EOF

echo "Etherpad settings.json created"
