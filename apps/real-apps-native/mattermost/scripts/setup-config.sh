#!/bin/bash
set -e

# AtRestEncryptKey must stay stable across redeploys — Mattermost encrypts data
# at rest with it, so rotating it makes previously encrypted data undecryptable.
# Hop3 generates it once and re-injects it unchanged via [env] (ADR 046); read
# that value here rather than minting a fresh key on every deploy.
: "${MM_ATRESTKEY:?ERROR: MM_ATRESTKEY is required (declare it as [env] { generate = \"base64\" } in hop3.toml)}"

cat > config/config.json << EOF
{
  "ServiceSettings": {
    "SiteURL": "${MM_SERVICESETTINGS_SITEURL:-http://localhost:${PORT:-8080}}",
    "ListenAddress": ":${PORT:-8080}",
    "ConnectionSecurity": "",
    "TLSCertFile": "",
    "TLSKeyFile": "",
    "EnableLocalMode": true,
    "LocalModeSocketLocation": "$(pwd)/mattermost_local.socket"
  },
  "TeamSettings": {
    "EnableOpenServer": false,
    "EnableUserCreation": false
  },
  "SqlSettings": {
    "DriverName": "postgres",
    "DataSource": "postgres://${PGUSER:-mattermost}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-mattermost}?sslmode=disable",
    "MaxIdleConns": 20,
    "MaxOpenConns": 300,
    "Trace": false,
    "AtRestEncryptKey": "${MM_ATRESTKEY}",
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
    "RequireEmailVerification": false,
    "EnableSignUpWithEmail": false
  },
  "PluginSettings": {
    "Enable": true,
    "Directory": "./plugins",
    "ClientDirectory": "./client/plugins"
  }
}
EOF
echo "Mattermost configuration created"
