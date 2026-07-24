<?php
// Hop3 WordPress configuration (nix-gen). Shipped via [nix].install-files and
// served from the writable cwd. Every setting is read with getenv() at request
// time, so the DB password is never baked onto disk; the salts come from stable
// [env] {generate=base64} secrets, re-injected identically on each redeploy.

// Database settings (from the mysql addon).
define('DB_NAME', getenv('MYSQL_DATABASE'));
define('DB_USER', getenv('MYSQL_USER'));
define('DB_PASSWORD', getenv('MYSQL_PASSWORD'));
define('DB_HOST', getenv('MYSQL_HOST') . ':' . getenv('MYSQL_PORT'));
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', '');

// Authentication keys and salts. Stable generated secrets ([env] in hop3.toml),
// re-injected identically on every redeploy — so hashed cookies and nonces
// survive a redeploy instead of logging every user out.
foreach ([
    'AUTH_KEY', 'SECURE_AUTH_KEY', 'LOGGED_IN_KEY', 'NONCE_KEY',
    'AUTH_SALT', 'SECURE_AUTH_SALT', 'LOGGED_IN_SALT', 'NONCE_SALT',
] as $hop3_salt) {
    define($hop3_salt, getenv($hop3_salt) ?: 'hop3-unset');
}

$table_prefix = 'wp_';
define('WP_DEBUG', getenv('WP_DEBUG') === 'true');

// Single-threaded `php -S` cannot serve WordPress's loopback wp-cron
// self-request while a page is rendering, so the spawn hangs and every request
// times out. Disable the pseudo-cron; the real fix is php-fpm (DEFERRED #16).
define('DISABLE_WP_CRON', true);

// Reverse-proxy awareness: honour X-Forwarded-Proto so WordPress builds https
// URLs behind Hop3's TLS-terminating nginx (otherwise admin/login redirect to
// http and break).
if (isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    $_SERVER['HTTPS'] = 'on';
}

// Derive the site URL from the incoming request host. The proxy routes only this
// app's own vhost here, so the request Host IS the hostname Hop3 assigned — this
// makes generated admin/login links resolve through the proxy and adapts if the
// domain changes, without a stored option the headless installer can't know.
if (!empty($_SERVER['HTTP_HOST'])) {
    $hop3_scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    define('WP_HOME', $hop3_scheme . '://' . $_SERVER['HTTP_HOST']);
    define('WP_SITEURL', $hop3_scheme . '://' . $_SERVER['HTTP_HOST']);
}

if (!defined('ABSPATH')) {
    define('ABSPATH', __DIR__ . '/');
}

require_once ABSPATH . 'wp-settings.php';
