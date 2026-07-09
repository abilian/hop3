#!/bin/bash
# Setup WordPress configuration from environment variables

set -e

# Use MySQL environment variables provided by Hop3 addon
DB_HOST="${MYSQL_HOST:-localhost}"
DB_NAME="${MYSQL_DATABASE:-wordpress}"
DB_USER="${MYSQL_USER:-wordpress}"
DB_PASS="${MYSQL_PASSWORD:-}"
WP_DEBUG="${WP_DEBUG:-false}"

# Generate salts if not provided
AUTH_KEY="${AUTH_KEY:-$(head -c 64 /dev/urandom | base64)}"
SECURE_AUTH_KEY="${SECURE_AUTH_KEY:-$(head -c 64 /dev/urandom | base64)}"
LOGGED_IN_KEY="${LOGGED_IN_KEY:-$(head -c 64 /dev/urandom | base64)}"
NONCE_KEY="${NONCE_KEY:-$(head -c 64 /dev/urandom | base64)}"
AUTH_SALT="${AUTH_SALT:-$(head -c 64 /dev/urandom | base64)}"
SECURE_AUTH_SALT="${SECURE_AUTH_SALT:-$(head -c 64 /dev/urandom | base64)}"
LOGGED_IN_SALT="${LOGGED_IN_SALT:-$(head -c 64 /dev/urandom | base64)}"
NONCE_SALT="${NONCE_SALT:-$(head -c 64 /dev/urandom | base64)}"

cat > wp-config.php << EOF
<?php
// WordPress configuration for Hop3 (auto-generated)

// Database settings
define('DB_NAME', '${DB_NAME}');
define('DB_USER', '${DB_USER}');
define('DB_PASSWORD', '${DB_PASS}');
define('DB_HOST', '${DB_HOST}');
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', '');

// Authentication keys and salts
define('AUTH_KEY', '${AUTH_KEY}');
define('SECURE_AUTH_KEY', '${SECURE_AUTH_KEY}');
define('LOGGED_IN_KEY', '${LOGGED_IN_KEY}');
define('NONCE_KEY', '${NONCE_KEY}');
define('AUTH_SALT', '${AUTH_SALT}');
define('SECURE_AUTH_SALT', '${SECURE_AUTH_SALT}');
define('LOGGED_IN_SALT', '${LOGGED_IN_SALT}');
define('NONCE_SALT', '${NONCE_SALT}');

// Table prefix
\$table_prefix = 'wp_';

// Debug mode
define('WP_DEBUG', ${WP_DEBUG});

// Absolute path to the WordPress directory
if (!defined('ABSPATH')) {
    define('ABSPATH', __DIR__ . '/');
}

// Load WordPress
require_once ABSPATH . 'wp-settings.php';
EOF

echo "WordPress wp-config.php created"

# --- Email: route wp_mail() through the Hop3 email backend, when attached. ---
# WordPress's wp_mail() uses PHP mail() and ignores the environment; an attached
# email addon injects SMTP_HOST (127.0.0.1 for the shared loopback relay, ADR
# 054). This must-use plugin points PHPMailer at it and self-disables when no
# addon is attached (no SMTP_HOST) — so a plain WordPress is never misconfigured
# and no app ever shells sendmail.
mkdir -p wp-content/mu-plugins
cat > wp-content/mu-plugins/hop3-smtp.php << 'PHPEOF'
<?php
/* Hop3: send wp_mail() via the platform email backend (SMTP). Auto-generated. */
add_action('phpmailer_init', function ($phpmailer) {
    $host = getenv('SMTP_HOST');
    if (!$host) {
        return;  // no email addon attached — leave WordPress's default mailer
    }
    $phpmailer->isSMTP();
    $phpmailer->Host = $host;
    $phpmailer->Port = (int) (getenv('SMTP_PORT') ?: 25);
    $user = getenv('SMTP_USER');
    if ($user) {
        $phpmailer->SMTPAuth = true;
        $phpmailer->Username = $user;
        $phpmailer->Password = getenv('SMTP_PASSWORD');
    } else {
        $phpmailer->SMTPAuth = false;   // loopback relay: no auth
    }
    $phpmailer->SMTPAutoTLS = false;    // no TLS toward the local relay
    $phpmailer->SMTPSecure = '';
    $from = getenv('SMTP_FROM');
    if ($from) {
        $phpmailer->setFrom($from, get_bloginfo('name'));
    }
}, 99);
PHPEOF

echo "WordPress SMTP mu-plugin installed (inert unless an email addon is attached)"
