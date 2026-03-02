#!/bin/bash
set -e
cat > config/config.json << EOF
{
  "ServiceSettings": {
    "SiteURL": "${MM_SERVICESETTINGS_SITEURL:-http://localhost:${PORT:-8080}}",
    "ListenAddress": ":${PORT:-8080}",
    "ConnectionSecurity": "",
    "TLSCertFile": "",
    "TLSKeyFile": "",
    "EnableLocalMode": false
  },
  "SqlSettings": {
    "DriverName": "postgres",
    "DataSource": "postgres://${PGUSER:-mattermost}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-mattermost}?sslmode=disable",
    "MaxIdleConns": 20,
    "MaxOpenConns": 300,
    "Trace": false,
    "AtRestEncryptKey": "$(head -c 32 /dev/urandom | base64)",
    "QueryTimeout": 30
  },
  "LogSettings": {
    "EnableConsole": true,
    "ConsoleLevel": "INFO",
    "EnableFile": false
  },
  "FileSettings": {
    "DriverName": "local",
    "Directory": "./data/"
  },
  "EmailSettings": {
    "SendEmailNotifications": false,
    "RequireEmailVerification": false
  },
  "PluginSettings": {
    "Enable": true,
    "Directory": "./plugins",
    "ClientDirectory": "./client/plugins"
  }
}
EOF
echo "Mattermost configuration created"
