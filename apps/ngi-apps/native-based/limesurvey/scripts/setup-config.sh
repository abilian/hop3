#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f application/config/config.php ]; then
    cat > application/config/config.php << EOF
<?php if (!defined('BASEPATH')) exit('No direct script access allowed');
return array(
    'components' => array(
        'db' => array(
            'connectionString' => 'pgsql:host=${PGHOST:-localhost};port=${PGPORT:-5432};dbname=${PGDATABASE:-limesurvey}',
            'username' => '${PGUSER:-limesurvey}',
            'password' => '${PGPASSWORD:-}',
            'charset' => 'utf8',
            'tablePrefix' => 'lime_',
        ),
        'urlManager' => array(
            'urlFormat' => 'path',
            'showScriptName' => true,
        ),
    ),
    'config' => array(
        'debug' => 0,
        'debugsql' => 0,
    )
);
EOF
    # Run CLI installer
    php application/commands/console.php install \
        "${ADMIN_USER:-admin}" \
        "${ADMIN_PASSWORD:-changeme}" \
        "${ADMIN_NAME:-Administrator}" \
        "${ADMIN_EMAIL:-admin@example.com}" || true
fi

echo "LimeSurvey configuration ready"
