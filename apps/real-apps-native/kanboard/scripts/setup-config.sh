#!/bin/bash
# Setup Kanboard configuration from environment variables

set -e

CONFIG_FILE="config.php"

# Use MySQL environment variables provided by Hop3 addon
DB_HOST="${MYSQL_HOST:-localhost}"
DB_PORT="${MYSQL_PORT:-3306}"
DB_USER="${MYSQL_USER:-kanboard}"
DB_PASS="${MYSQL_PASSWORD:-}"
DB_NAME="${MYSQL_DATABASE:-kanboard}"

cat > "$CONFIG_FILE" << EOF
<?php
// Kanboard configuration for Hop3 (auto-generated)

// Database configuration
define('DB_DRIVER', 'mysql');
define('DB_HOST', '${DB_HOST}');
define('DB_PORT', '${DB_PORT}');
define('DB_USERNAME', '${DB_USER}');
define('DB_PASSWORD', '${DB_PASS}');
define('DB_NAME', '${DB_NAME}');

// Enable plugins
define('PLUGIN_INSTALLER', true);

// Enable debug if set
define('DEBUG', ${DEBUG:-false});

// Logging
define('LOG_DRIVER', 'stderr');
EOF

echo "Kanboard configuration created"
