#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PORT:?ERROR: PORT is required}"
: "${DATABASE_URL:?ERROR: DATABASE_URL is required}"

cd /opt/mattermost

# Configure database from Hop3 env vars
export MM_SQLSETTINGS_DRIVERNAME="postgres"
export MM_SQLSETTINGS_DATASOURCE="${DATABASE_URL}"

# Listen on PORT
export MM_SERVICESETTINGS_LISTENADDRESS=":${PORT}"

# Run as mattermost user
exec su mattermost -c "cd /opt/mattermost && ./bin/mattermost"
