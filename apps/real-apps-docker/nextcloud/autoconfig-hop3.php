<?php
/**
 * Nextcloud Auto Configuration for Hop3
 *
 * This file is used for initial Nextcloud setup.
 * It will be processed once during first access.
 */

$AUTOCONFIG = array(
    // Database configuration (PostgreSQL)
    // Required: PG* env vars are validated by startup script before Apache starts
    'dbtype' => 'pgsql',
    'dbname' => getenv('PGDATABASE'),
    'dbuser' => getenv('PGUSER'),
    'dbpass' => getenv('PGPASSWORD'),
    'dbhost' => getenv('PGHOST'),
    'dbtableprefix' => 'oc_',

    // Admin account (optional - defaults provided)
    'adminlogin' => getenv('NEXTCLOUD_ADMIN_USER') ?: 'admin',
    'adminpass' => getenv('NEXTCLOUD_ADMIN_PASSWORD') ?: '',

    // Data directory (optional - default provided)
    'directory' => getenv('NEXTCLOUD_DATA_DIR') ?: './data',
);
