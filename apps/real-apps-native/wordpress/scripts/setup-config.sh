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

// Disable WordPress's built-in pseudo-cron. On every page load WordPress spawns
// a non-blocking loopback request to wp-cron.php; against the single-threaded
// \`php -S\` runtime that self-request cannot be served while the page is being
// rendered, so the spawn's connect hangs and EVERY request times out (even the
// front page). Disabling it makes the site responsive. The real fix is php-fpm
// (DEFERRED-APPS.md #16); once that lands, trigger wp-cron from a system cron
// hitting wp-cron.php instead.
define('DISABLE_WP_CRON', true);

// Reverse-proxy awareness. Hop3's nginx terminates TLS and forwards the real
// scheme via X-Forwarded-Proto; honour it so WordPress builds https URLs behind
// TLS (otherwise it redirects admin/login to http and they break).
if (isset(\$_SERVER['HTTP_X_FORWARDED_PROTO']) && \$_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    \$_SERVER['HTTPS'] = 'on';
}

// Derive the site URL from the incoming request (host + scheme) instead of a
// stored option. The headless CLI installer can't know the public hostname, and
// the reverse proxy only routes this app's own vhost here — so the request Host
// IS the hostname Hop3 assigned (HOST_NAME). This makes every generated admin/
// login link resolve through the proxy rather than the installer's guessed
// 'localhost', and adapts automatically if the domain changes.
if (!empty(\$_SERVER['HTTP_HOST'])) {
    \$hop3_scheme = (!empty(\$_SERVER['HTTPS']) && \$_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    define('WP_HOME', \$hop3_scheme . '://' . \$_SERVER['HTTP_HOST']);
    define('WP_SITEURL', \$hop3_scheme . '://' . \$_SERVER['HTTP_HOST']);
}

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

# --- Headless install: create the schema + first admin without the browser
# wizard (ADR 056). The platform generates the admin password once and injects
# HOP3_ADMIN_USER/EMAIL/PASSWORD; hop3.toml maps them to WP_ADMIN_* via
# [env.computed], and wp-install.php calls WordPress's core wp_install().
#
# Idempotency + connectivity gate: probe for the wp_users table. Fail LOUD if
# the database is unreachable (never mistake "can't connect" for "fresh install"
# and silently re-install). WordPress uses the mysqli extension, so does this.
installed=$(php -r '
$h = getenv("MYSQL_HOST") ?: "localhost";
$p = (int) (getenv("MYSQL_PORT") ?: 3306);
$d = getenv("MYSQL_DATABASE") ?: "wordpress";
$u = getenv("MYSQL_USER") ?: "wordpress";
$w = getenv("MYSQL_PASSWORD") ?: "";
mysqli_report(MYSQLI_REPORT_OFF);
$c = @mysqli_connect($h, $u, $w, $d, $p);
if (!$c) { fwrite(STDERR, "DB probe failed: " . mysqli_connect_error() . "\n"); echo "error"; exit; }
$q = "SELECT 1 FROM information_schema.tables WHERE table_schema = \x27"
   . $c->real_escape_string($d) . "\x27 AND table_name = \x27wp_users\x27 LIMIT 1";
$r = $c->query($q);
echo ($r && $r->num_rows > 0) ? "yes" : "no";
')

if [ "$installed" = "error" ]; then
    echo "WordPress setup can't probe database: connection failed, aborting" >&2
    exit 1
fi

if [ "$installed" = "no" ]; then
    echo "Installing WordPress (headless)..."
    # Fail loud on any missing credential (no ':-default' fallback); a non-zero
    # installer exit aborts the deploy via 'set -e' (no '|| true').
    WP_ADMIN_USER="${WP_ADMIN_USER:?WP_ADMIN_USER not set (expected from HOP3_ADMIN_USER via [admin] + [env.computed])}" \
    WP_ADMIN_EMAIL="${WP_ADMIN_EMAIL:?WP_ADMIN_EMAIL not set (expected from HOP3_ADMIN_EMAIL via [admin] + [env.computed])}" \
    WP_ADMIN_PASSWORD="${WP_ADMIN_PASSWORD:?WP_ADMIN_PASSWORD not set (expected from HOP3_ADMIN_PASSWORD via [admin] + [env.computed])}" \
    WP_TITLE="${WP_TITLE:-WordPress}" \
        php scripts/wp-install.php
    echo "WordPress admin account created"
else
    echo "WordPress already installed, skipping install"
fi

echo "WordPress configuration ready"
