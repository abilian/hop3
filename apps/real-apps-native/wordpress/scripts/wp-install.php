<?php
/**
 * Hop3: headless WordPress install (schema + first admin) — no browser wizard.
 *
 * Mirrors wp-admin/install.php's bootstrap: define WP_INSTALLING so WordPress
 * boots against an empty database without redirecting to the setup wizard, then
 * call the core wp_install() — the very routine WP-CLI's `wp core install` runs
 * under the hood (WP-CLI is not bundled here, so we call core directly).
 *
 * Idempotent: a second run is a no-op via is_blog_installed(). Fails LOUD (exit
 * 1) on a missing credential or a WP_Error, so a broken install aborts the
 * deploy instead of greening. Connectivity is already gated by the shell probe
 * in setup-config.sh before this script is invoked.
 */

error_reporting(E_ERROR | E_PARSE);

if (!defined('WP_INSTALLING')) {
    define('WP_INSTALLING', true);
}

require_once __DIR__ . '/../wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';

if (is_blog_installed()) {
    echo "WordPress already installed\n";
    exit(0);
}

$title = getenv('WP_TITLE') ?: 'WordPress';
$user  = getenv('WP_ADMIN_USER');
$email = getenv('WP_ADMIN_EMAIL');
$pass  = getenv('WP_ADMIN_PASSWORD');

foreach (
    [
        'WP_ADMIN_USER' => $user,
        'WP_ADMIN_EMAIL' => $email,
        'WP_ADMIN_PASSWORD' => $pass,
    ] as $name => $val
) {
    if ($val === false || $val === '') {
        fwrite(
            STDERR,
            "WordPress install: {$name} is required "
            . "(injected via HOP3_ADMIN_* + [env.computed])\n"
        );
        exit(1);
    }
}

// $is_public = true; $deprecated = ''; password passed explicitly.
$result = wp_install($title, $user, $email, true, '', $pass);

if (is_wp_error($result)) {
    fwrite(
        STDERR,
        "WordPress install failed: " . $result->get_error_message() . "\n"
    );
    exit(1);
}

echo "WordPress installed (admin user '{$user}')\n";
exit(0);
