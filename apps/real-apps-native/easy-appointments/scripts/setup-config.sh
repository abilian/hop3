#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Public URL: prefer the host Hop3 assigned (HOP3_PUBLIC_URL = https://<host>),
# fall back to APP_URL, then localhost (Docker e2e has no domain). Re-applied on
# every deploy so a domain change takes effect in Easy!Appointments' BASE_URL,
# which the app uses for redirects and asset URLs.
BASE_URL_VALUE="${HOP3_PUBLIC_URL:-${APP_URL:-http://localhost:8080}}"

# (Re)generate config.php from the sample every deploy so BASE_URL and the DB
# credentials always reflect the current environment (idempotent: same env ->
# same file; config.php holds no state that must persist across deploys).
cp -f config-sample.php config.php
sed -i "s|BASE_URL.*|BASE_URL = '${BASE_URL_VALUE}';|" config.php
sed -i "s|DB_HOST.*|DB_HOST = '${MYSQL_HOST:-localhost}';|" config.php
sed -i "s|DB_NAME.*|DB_NAME = '${MYSQL_DATABASE:-easyappointments}';|" config.php
sed -i "s|DB_USERNAME.*|DB_USERNAME = '${MYSQL_USER:-easyappointments}';|" config.php
sed -i "s|DB_PASSWORD.*|DB_PASSWORD = '${MYSQL_PASSWORD:-}';|" config.php

# Probe the database for the schema (ea_users table — the same check E!A's own
# is_app_installed() makes, with the ea_ table prefix) so a redeploy against an
# already-populated database is a no-op instead of a re-install error. Uses
# mysqli, the driver E!A itself requires.
installed=$(php -r '
mysqli_report(MYSQLI_REPORT_OFF);
$c = @mysqli_connect(
    getenv("MYSQL_HOST") ?: "localhost",
    getenv("MYSQL_USER") ?: "easyappointments",
    getenv("MYSQL_PASSWORD") ?: "",
    getenv("MYSQL_DATABASE") ?: "easyappointments",
    (int) (getenv("MYSQL_PORT") ?: 3306)
);
if (!$c) {
    fwrite(STDERR, "DB probe failed: " . mysqli_connect_error() . "\n");
    echo "error";
    exit;
}
$r = mysqli_query($c, "SHOW TABLES LIKE \x27ea_users\x27");
echo ($r && mysqli_num_rows($r) > 0) ? "yes" : "no";
')

if [ "$installed" = "error" ]; then
    echo "Easy!Appointments setup can't probe database: connection failed, aborting" >&2
    exit 1
fi

if [ "$installed" = "no" ]; then
    echo "Installing Easy!Appointments (schema + admin)..."
    # Headless install: builds the schema and seeds the initial admin + demo
    # provider/service/customer. Fails loud — a migration error exits non-zero
    # and 'set -e' aborts the deploy (no '|| true').
    php index.php console install

    # console install seeds a fixed admin ("administrator" / "administrator").
    # Re-key it to the credentials Hop3 generated and injected (ADR-056). Fail
    # loud on any missing credential (never fall back to a default).
    : "${EA_ADMIN_USERNAME:?EA_ADMIN_USERNAME not set (expected from HOP3_ADMIN_USER via [admin] + [env.computed])}"
    : "${EA_ADMIN_EMAIL:?EA_ADMIN_EMAIL not set (expected from HOP3_ADMIN_EMAIL)}"
    : "${EA_ADMIN_PASSWORD:?EA_ADMIN_PASSWORD not set (expected from HOP3_ADMIN_PASSWORD)}"
    php scripts/reconcile-admin.php
    echo "Easy!Appointments installed and admin configured"
else
    echo "Easy!Appointments already installed, skipping install"
fi

echo "Easy!Appointments configuration ready"
