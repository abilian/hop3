#!/bin/bash
set -e

# Ensure we're in the Nextcloud directory
cd "$(dirname "$0")/.."

# The mysql addon must have provisioned. These used to default
# (${MYSQL_HOST:-localhost}, ${MYSQL_DATABASE:-nextcloud}), so a missing addon
# produced an install pointed at a database that does not exist instead of an
# error — and Nextcloud then quietly fell back to SQLite.
: "${MYSQL_HOST:?the mysql addon did not provision MYSQL_HOST}"
: "${MYSQL_DATABASE:?the mysql addon did not provision MYSQL_DATABASE}"
: "${MYSQL_USER:?the mysql addon did not provision MYSQL_USER}"
: "${MYSQL_PASSWORD:?the mysql addon did not provision MYSQL_PASSWORD}"

# Install once (idempotent: skip when already installed).
if php occ status 2>/dev/null | grep -q "installed: true"; then
    echo "Nextcloud already installed"
else
    echo "Installing Nextcloud..."
    php occ maintenance:install \
        --database="mysql" \
        --database-host="${MYSQL_HOST}" \
        --database-port="${MYSQL_PORT:-3306}" \
        --database-name="${MYSQL_DATABASE}" \
        --database-user="${MYSQL_USER}" \
        --database-pass="${MYSQL_PASSWORD}" \
        --admin-user="${NEXTCLOUD_ADMIN_USER:?NEXTCLOUD_ADMIN_USER is required (set via [admin] username + [env.computed])}" \
        --admin-pass="${NEXTCLOUD_ADMIN_PASSWORD:?NEXTCLOUD_ADMIN_PASSWORD is required (set via [admin] password generate + [env.computed])}" \
        --data-dir="$(pwd)/data"
    echo "Nextcloud installed successfully"
fi

# Verify the EFFECT, not the exit code. `maintenance:install` can complete while
# falling back to SQLite — which is how this app shipped with dbtype=sqlite3 and
# MySQL connection parameters sitting unused beside it. Nextcloud itself warns
# that SQLite is unsuitable for production and breaks file sync, so a silent
# fallback is a broken deploy, not a degraded one.
dbtype=$(php occ config:system:get dbtype 2>/dev/null || echo "unknown")
if [ "$dbtype" != "mysql" ]; then
    echo "Nextcloud installed on '$dbtype', not the MySQL addon it was given." >&2
    echo "Refusing to report success: SQLite is unsupported for production use" >&2
    echo "and file syncing misbehaves on it." >&2
    echo "An instance already holding data can be migrated in place with:" >&2
    echo "  php occ db:convert-type --all-apps mysql \"$MYSQL_USER\" \"$MYSQL_HOST\" \"$MYSQL_DATABASE\"" >&2
    exit 1
fi

# Trust the loopback AND the public hostname(s) Hop3 assigned — re-applied every
# deploy so a domain change takes effect. Without the real host in
# trusted_domains, Nextcloud rejects every request through the reverse proxy
# with "Access through untrusted domain" (HTTP 400) and the login is unreachable.
php occ config:system:set trusted_domains 0 --value="localhost"
if [ -n "${HOST_NAME:-}" ] && [ "${HOST_NAME}" != "_" ]; then
    i=1
    for host in ${HOST_NAME//,/ }; do
        php occ config:system:set trusted_domains "$i" --value="$host"
        i=$((i + 1))
    done
fi

# Tell Nextcloud it sits behind Hop3's TLS-terminating reverse proxy.
#
# PHP sees a plain-HTTP request from the proxy, so without this Nextcloud builds
# http:// URLs for its own assets, redirects, and CSRF checks. Served over HTTPS
# that mismatch breaks the login POST — the credentials are correct, but the
# request is rejected — and the browser reports it as a bad password.
# `overwrite.cli.url` additionally defaults to http://localhost, which puts the
# wrong URL in every notification email and generated link.
#
# Re-applied every deploy (like trusted_domains above) so a domain change takes
# effect, and so an instance installed before this existed is repaired.
public_url="${HOP3_PUBLIC_URL:-}"
case "$public_url" in
    https://*)
        php occ config:system:set overwriteprotocol --value="https"
        php occ config:system:set overwrite.cli.url --value="$public_url"
        # The proxy is the only thing that talks to the app (the port is bound
        # to loopback), so trusting it is what lets Nextcloud read the real
        # client IP from X-Forwarded-For instead of seeing every visitor as
        # 127.0.0.1 — which its rate limiting and brute-force protection use.
        php occ config:system:set trusted_proxies 0 --value="127.0.0.1"
        ;;
    *)
        # Serving over plain HTTP ([deploy].allow-http) or no domain yet: leave
        # the protocol override off rather than asserting an HTTPS we do not have.
        php occ config:system:delete overwriteprotocol 2>/dev/null || true
        ;;
esac

echo "Nextcloud configuration ready"
