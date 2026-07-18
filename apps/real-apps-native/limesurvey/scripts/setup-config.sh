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
fi

# Probe the database for the schema (lime_users table) so that redeploys against
# an already-populated database are idempotent. The postgres addon provides the
# PG* connection env vars; pdo_pgsql is required by LimeSurvey itself.
installed=$(php -r '
$h = getenv("PGHOST") ?: "localhost";
$p = getenv("PGPORT") ?: "5432";
$d = getenv("PGDATABASE") ?: "limesurvey";
$u = getenv("PGUSER") ?: "limesurvey";
$w = getenv("PGPASSWORD") ?: "";
try {
    $pdo = new PDO("pgsql:host=$h;port=$p;dbname=$d", $u, $w);
    $r = $pdo->query("SELECT to_regclass(\x27public.lime_users\x27)")->fetchColumn();
    echo $r ? "yes" : "no";
} catch (Throwable $e) {
    fwrite(STDERR, "DB probe failed: " . $e->getMessage() . "\n");
    echo "error";
}
')

if [ "$installed" = "error" ]; then
    echo "LimeSurvey setup can't probe database: connection failed, aborting" >&2
    exit 1
fi

if [ "$installed" = "no" ]; then
    # Fail loud on any missing credential (never fall back to a default) and let
    # a non-zero installer exit abort the deploy via 'set -e' (no '|| true').
    php application/commands/console.php install \
        "${ADMIN_USER:?ADMIN_USER not set (expected from HOP3_ADMIN_USER)}" \
        "${ADMIN_PASSWORD:?ADMIN_PASSWORD not set (expected from HOP3_ADMIN_PASSWORD)}" \
        "${ADMIN_NAME:-Administrator}" \
        "${ADMIN_EMAIL:?ADMIN_EMAIL not set (expected from HOP3_ADMIN_EMAIL)}"
    echo "LimeSurvey admin account created"
else
    echo "LimeSurvey already installed, skipping install"
fi

echo "LimeSurvey configuration ready"
