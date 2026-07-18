#!/bin/bash
set -e
cd "$(dirname "$0")/.."

mkdir -p data

# config.local.php MUST declare `namespace Paheko;`. Without it, `const DB_FILE`
# etc. define *global* constants that Paheko never reads (it looks up
# Paheko\DB_FILE), so it silently falls back to its defaults and the settings
# below are ignored. See config.dist.php ("Nécessaire pour situer les constantes
# dans le bon namespace").
if [ ! -f config.local.php ]; then
    cat > config.local.php <<EOF
<?php
namespace Paheko;
const DATA_ROOT = __DIR__ . '/data';
const DB_FILE = DATA_ROOT . '/paheko.sqlite';
const SECRET_KEY = '$(head -c 32 /dev/urandom | base64)';
EOF
fi

DB_FILE="data/paheko.sqlite"

# Idempotency probe: is Paheko already installed? Mirrors DB::isInstalled()
# (a non-empty DB file) and additionally verifies the schema by checking for the
# `config` table created by the installer. This makes a redeploy a no-op instead
# of the "Database file already exists" error that `paheko init` would raise.
installed=$(php -r '
$f = $argv[1];
if (!is_file($f) || !filesize($f)) { echo "no"; exit; }
try {
    $db = new SQLite3($f, SQLITE3_OPEN_READONLY);
    $r = $db->querySingle("SELECT name FROM sqlite_master WHERE type = \x27table\x27 AND name = \x27config\x27");
    echo $r ? "yes" : "no";
} catch (\Throwable $e) {
    fwrite(STDERR, "Paheko DB probe failed: " . $e->getMessage() . "\n");
    echo "error";
}
' "$DB_FILE")

if [ "$installed" = "error" ]; then
    echo "Paheko setup can't probe database: connection failed, aborting" >&2
    exit 1
fi

if [ "$installed" = "no" ]; then
    # Headless install (ADR 056): create the schema and the first admin in one
    # pass, no browser wizard. Fail loud on any missing credential (never fall
    # back to a default) and let a non-zero installer exit abort the deploy via
    # 'set -e' (no '|| true'). The password is passed via a mode-600 file so it
    # never appears in argv / `ps` output (the CLI itself recommends this).
    PW_FILE="$(mktemp)"
    chmod 600 "$PW_FILE"
    trap 'rm -f "$PW_FILE"' EXIT
    printf '%s' "${HOP3_ADMIN_PASSWORD:?HOP3_ADMIN_PASSWORD not set (expected from [admin] password generate)}" > "$PW_FILE"

    php bin/paheko init \
        --country "${PAHEKO_COUNTRY:-FR}" \
        --orgname "${PAHEKO_ORG_NAME:-Paheko}" \
        --name "${HOP3_ADMIN_USER:?HOP3_ADMIN_USER not set (expected from [admin] username)}" \
        --email "${HOP3_ADMIN_EMAIL:?HOP3_ADMIN_EMAIL not set (expected from [admin] email)}" \
        --password-file "$PW_FILE"

    echo "Paheko installed (schema + admin account created)"
else
    echo "Paheko already installed, skipping install"
fi

echo "Paheko configuration ready"
