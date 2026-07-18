#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Invoice Ninja reads its DB + app config from .env. Regenerate it each deploy
# from the addon-provided MYSQL_* vars and the platform's public URL. APP_URL is
# taken from the injected HOP3_PUBLIC_URL (https://<host>) so the SPA points its
# API base at the reverse-proxy hostname; falls back to localhost when the app
# has no domain yet (e.g. a bare Docker test target).
cat > .env << EOF
APP_KEY=$(php artisan key:generate --show 2>/dev/null || echo "base64:$(head -c 32 /dev/urandom | base64)")
APP_URL=${HOP3_PUBLIC_URL:-http://localhost:${PORT:-8080}}
APP_ENV=production
APP_DEBUG=false
DB_CONNECTION=mysql
DB_HOST=${MYSQL_HOST:-localhost}
DB_PORT=${MYSQL_PORT:-3306}
DB_DATABASE=${MYSQL_DATABASE:-invoiceninja}
DB_USERNAME=${MYSQL_USER:-invoiceninja}
DB_PASSWORD=${MYSQL_PASSWORD:-}
REQUIRE_HTTPS=false
EOF

# Create the schema (idempotent: only pending migrations run).
php artisan migrate --force

# Probe the DB for a completed install (an accounts row) so a redeploy is a
# no-op instead of creating a SECOND account — ninja:create-account is not itself
# idempotent. Invoice Ninja requires pdo_mysql, so the probe can use it too.
installed=$(php -r '
$h = getenv("MYSQL_HOST") ?: "localhost";
$p = getenv("MYSQL_PORT") ?: "3306";
$d = getenv("MYSQL_DATABASE") ?: "invoiceninja";
$u = getenv("MYSQL_USER") ?: "invoiceninja";
$w = getenv("MYSQL_PASSWORD") ?: "";
try {
    $pdo = new PDO("mysql:host=$h;port=$p;dbname=$d", $u, $w);
    $t = $pdo->query("SHOW TABLES LIKE \x27accounts\x27")->fetchColumn();
    if (!$t) {
        echo "no";
    } else {
        $c = (int) $pdo->query("SELECT COUNT(*) FROM accounts")->fetchColumn();
        echo $c > 0 ? "yes" : "no";
    }
} catch (Throwable $e) {
    fwrite(STDERR, "DB probe failed: " . $e->getMessage() . "\n");
    echo "error";
}
')

if [ "$installed" = "error" ]; then
    echo "Invoice Ninja setup can't probe database: connection failed, aborting" >&2
    exit 1
fi

if [ "$installed" = "no" ]; then
    # Seed the reference tables (currencies, countries, payment types, ...) that
    # the app and the first account depend on. Without this, migrate leaves those
    # tables empty and the app 500s on use. Internally idempotent (guarded on an
    # existing timezone row), so re-running is safe.
    php artisan db:seed --force

    # Create the first account + admin user headlessly from the injected ADR-056
    # credentials (Invoice Ninja keys admins by email, no username). Fail loud on
    # a missing var (never a default) and let a non-zero exit abort the deploy via
    # 'set -e' (no '|| true').
    php artisan ninja:create-account \
        --email="${HOP3_ADMIN_EMAIL:?HOP3_ADMIN_EMAIL not set (declare [admin].email in hop3.toml)}" \
        --password="${HOP3_ADMIN_PASSWORD:?HOP3_ADMIN_PASSWORD not set (declare [admin].password in hop3.toml)}"
    echo "Invoice Ninja admin account created"
else
    echo "Invoice Ninja already installed, skipping account creation"
fi

php artisan optimize
echo "Invoice Ninja configuration ready"
