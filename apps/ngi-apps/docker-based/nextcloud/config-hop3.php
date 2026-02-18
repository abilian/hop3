<?php
/**
 * Nextcloud Configuration for Hop3
 *
 * This file contains additional configuration that should be merged
 * into config/config.php after initial setup.
 */

$CONFIG = array(
    // Trusted domains (set via environment variable)
    'trusted_domains' => array_filter(
        array_merge(
            ['localhost'],
            explode(',', getenv('NEXTCLOUD_TRUSTED_DOMAINS') ?: '')
        )
    ),

    // Proxy settings for Hop3 nginx
    'overwriteprotocol' => getenv('OVERWRITEPROTOCOL') ?: 'https',
    'overwrite.cli.url' => getenv('NEXTCLOUD_URL') ?: '',
    'trusted_proxies' => ['127.0.0.1', '::1'],
    'forwarded_for_headers' => ['HTTP_X_FORWARDED_FOR'],

    // Redis caching (if Redis addon is attached)
    'memcache.local' => '\\OC\\Memcache\\APCu',
    'memcache.distributed' => getenv('REDIS_HOST') ? '\\OC\\Memcache\\Redis' : null,
    'memcache.locking' => getenv('REDIS_HOST') ? '\\OC\\Memcache\\Redis' : null,
    'redis' => getenv('REDIS_HOST') ? array(
        'host' => getenv('REDIS_HOST'),
        'port' => (int)(getenv('REDIS_PORT') ?: 6379),
        'password' => getenv('REDIS_PASSWORD') ?: '',
    ) : null,

    // Performance
    'filelocking.enabled' => true,
    'default_phone_region' => 'FR',

    // Logging
    'log_type' => 'file',
    'logfile' => './data/nextcloud.log',
    'loglevel' => (int)(getenv('NEXTCLOUD_LOGLEVEL') ?: 2),
    'logdateformat' => 'Y-m-d H:i:s',

    // Security
    'csrf.optout' => [],

    // Background jobs
    'backgroundjobs_mode' => 'cron',

    // Email (configure via environment)
    'mail_smtpmode' => getenv('SMTP_HOST') ? 'smtp' : 'sendmail',
    'mail_smtphost' => getenv('SMTP_HOST') ?: '',
    'mail_smtpport' => (int)(getenv('SMTP_PORT') ?: 587),
    'mail_smtpsecure' => getenv('SMTP_SECURE') ?: 'tls',
    'mail_smtpauth' => (bool)getenv('SMTP_USER'),
    'mail_smtpname' => getenv('SMTP_USER') ?: '',
    'mail_smtppassword' => getenv('SMTP_PASSWORD') ?: '',
    'mail_from_address' => getenv('MAIL_FROM_ADDRESS') ?: 'nextcloud',
    'mail_domain' => getenv('MAIL_DOMAIN') ?: '',
);

// Remove null values
$CONFIG = array_filter($CONFIG, fn($v) => $v !== null);
