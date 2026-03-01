<?php
/**
 * WordPress Configuration for Hop3
 *
 * This configuration uses environment variables for all sensitive settings,
 * making it suitable for deployment on Hop3.
 *
 * @package WordPress
 */

// ** Database settings - provided by Hop3 MySQL addon ** //
// Required: MYSQL_* env vars are validated by startup script before Apache starts
define( 'DB_NAME', getenv('MYSQL_DATABASE') );
define( 'DB_USER', getenv('MYSQL_USER') );
define( 'DB_PASSWORD', getenv('MYSQL_PASSWORD') );
define( 'DB_HOST', getenv('MYSQL_HOST') );
define( 'DB_CHARSET', 'utf8mb4' );
define( 'DB_COLLATE', '' );

/**
 * Authentication unique keys and salts.
 *
 * Generate these using: https://api.wordpress.org/secret-key/1.1/salt/
 * Or set via environment variables.
 */
define( 'AUTH_KEY',         getenv('WORDPRESS_AUTH_KEY') ?: 'put your unique phrase here' );
define( 'SECURE_AUTH_KEY',  getenv('WORDPRESS_SECURE_AUTH_KEY') ?: 'put your unique phrase here' );
define( 'LOGGED_IN_KEY',    getenv('WORDPRESS_LOGGED_IN_KEY') ?: 'put your unique phrase here' );
define( 'NONCE_KEY',        getenv('WORDPRESS_NONCE_KEY') ?: 'put your unique phrase here' );
define( 'AUTH_SALT',        getenv('WORDPRESS_AUTH_SALT') ?: 'put your unique phrase here' );
define( 'SECURE_AUTH_SALT', getenv('WORDPRESS_SECURE_AUTH_SALT') ?: 'put your unique phrase here' );
define( 'LOGGED_IN_SALT',   getenv('WORDPRESS_LOGGED_IN_SALT') ?: 'put your unique phrase here' );
define( 'NONCE_SALT',       getenv('WORDPRESS_NONCE_SALT') ?: 'put your unique phrase here' );

/**
 * WordPress database table prefix.
 */
$table_prefix = getenv('WORDPRESS_TABLE_PREFIX') ?: 'wp_';

/**
 * WordPress debugging mode.
 */
define( 'WP_DEBUG', filter_var(getenv('WP_DEBUG'), FILTER_VALIDATE_BOOLEAN) );
define( 'WP_DEBUG_LOG', filter_var(getenv('WP_DEBUG_LOG'), FILTER_VALIDATE_BOOLEAN) );
define( 'WP_DEBUG_DISPLAY', false );

/**
 * Site URL configuration.
 * Set these via environment variables for proper URL handling behind reverse proxy.
 */
if ( getenv('WORDPRESS_HOME') ) {
    define( 'WP_HOME', getenv('WORDPRESS_HOME') );
}
if ( getenv('WORDPRESS_SITEURL') ) {
    define( 'WP_SITEURL', getenv('WORDPRESS_SITEURL') );
}

/**
 * Handle reverse proxy headers (for Hop3 nginx proxy).
 */
if ( isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https' ) {
    $_SERVER['HTTPS'] = 'on';
}
if ( isset($_SERVER['HTTP_X_FORWARDED_HOST']) ) {
    $_SERVER['HTTP_HOST'] = $_SERVER['HTTP_X_FORWARDED_HOST'];
}

/**
 * Disable file editing in admin (security best practice).
 */
define( 'DISALLOW_FILE_EDIT', true );

/**
 * Limit post revisions to save database space.
 */
define( 'WP_POST_REVISIONS', 10 );

/**
 * Set memory limits.
 */
define( 'WP_MEMORY_LIMIT', '256M' );
define( 'WP_MAX_MEMORY_LIMIT', '512M' );

/**
 * Automatic updates configuration.
 */
define( 'WP_AUTO_UPDATE_CORE', 'minor' );

/* That's all, stop editing! Happy publishing. */

/** Absolute path to the WordPress directory. */
if ( ! defined( 'ABSPATH' ) ) {
    define( 'ABSPATH', __DIR__ . '/' );
}

/** Sets up WordPress vars and included files. */
require_once ABSPATH . 'wp-settings.php';
