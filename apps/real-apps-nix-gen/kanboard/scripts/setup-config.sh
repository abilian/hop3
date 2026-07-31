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
//
// Every constant is guarded with defined() || define(). A bare define() emits a
// warning when the file is included twice, PHP writes that warning to the
// response BEFORE any header, and Set-Cookie is then impossible — so the
// session never starts, the CSRF token never persists, and the login form
// reports "The username is required" for a credential that is correct.

// Database configuration
defined('DB_DRIVER') || define('DB_DRIVER', 'mysql');
defined('DB_HOST') || define('DB_HOST', '${DB_HOST}');
defined('DB_PORT') || define('DB_PORT', '${DB_PORT}');
defined('DB_USERNAME') || define('DB_USERNAME', '${DB_USER}');
defined('DB_PASSWORD') || define('DB_PASSWORD', '${DB_PASS}');
defined('DB_NAME') || define('DB_NAME', '${DB_NAME}');

// Disable the web plugin installer: it lets a logged-in admin install arbitrary
// plugin code from the internet (remote-code-execution vector). Keep it off.
defined('PLUGIN_INSTALLER') || define('PLUGIN_INSTALLER', false);

// Enable debug if set
defined('DEBUG') || define('DEBUG', ${DEBUG:-false});

// Logging
defined('LOG_DRIVER') || define('LOG_DRIVER', 'stderr');
EOF

echo "Kanboard configuration created"
