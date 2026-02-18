<?php
/**
 * Nextcloud Auto Configuration for Hop3
 *
 * This file is used for initial Nextcloud setup.
 * It will be processed once during first access.
 */

$AUTOCONFIG = array(
    // Database configuration (PostgreSQL)
    // Hop3 PostgreSQL addon provides PG* env vars, but also support POSTGRES_* for compatibility
    'dbtype' => 'pgsql',
    'dbname' => getenv('PGDATABASE') ?: getenv('POSTGRES_DB') ?: 'nextcloud',
    'dbuser' => getenv('PGUSER') ?: getenv('POSTGRES_USER') ?: 'nextcloud',
    'dbpass' => getenv('PGPASSWORD') ?: getenv('POSTGRES_PASSWORD') ?: '',
    'dbhost' => getenv('PGHOST') ?: getenv('POSTGRES_HOST') ?: 'localhost',
    'dbtableprefix' => 'oc_',

    // Admin account
    'adminlogin' => getenv('NEXTCLOUD_ADMIN_USER') ?: 'admin',
    'adminpass' => getenv('NEXTCLOUD_ADMIN_PASSWORD') ?: '',

    // Data directory
    'directory' => getenv('NEXTCLOUD_DATA_DIR') ?: './data',
);
