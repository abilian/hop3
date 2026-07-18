#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Isso's moderation/admin dashboard authenticates by PASSWORD ONLY (no username).
# The password is Hop3's generated admin credential, injected as
# HOP3_ADMIN_PASSWORD by the [admin] block in hop3.toml. Fail LOUD if it is
# absent: deploying with an unprotected/disabled admin surface (or an empty
# password) is a false success, not a working app.
ADMIN_PASSWORD="${HOP3_ADMIN_PASSWORD:?HOP3_ADMIN_PASSWORD not injected — [admin] block missing or admin bootstrap did not run}"

# Public site URL for CORS. Isso whitelists comment POSTs by Origin against
# [general] host; with host=localhost it rejects POSTs from the real frontend.
# Use the app's canonical public URL when Hop3 assigned a domain, and fall back
# to the loopback listen address otherwise (e.g. Docker tests with no domain).
# Not a credential, so a default is correct here.
ISSO_HOST="${HOP3_PUBLIC_URL:-http://localhost:${PORT:-8080}}"

mkdir -p data

# Re-template on EVERY deploy (never write-once): a stale isso.cfg from a prior
# deploy would otherwise keep the admin dashboard disabled and moderation off,
# so the security config would silently never take effect on redeploy.
cat > isso.cfg << EOF
[general]
dbpath = data/comments.db
host = ${ISSO_HOST}

[server]
listen = http://0.0.0.0:${PORT:-8080}
public-endpoint = ${ISSO_HOST}

# Password-protected moderation/admin dashboard at /admin/ (login POST /login/).
# Isso has no admin username; the password IS the credential.
[admin]
enabled = true
password = ${ADMIN_PASSWORD}

# Hold new comments in a moderation queue instead of publishing them instantly,
# so an anonymous visitor can't self-publish — the isso analog of closing open
# registration. An authenticated admin approves them from the dashboard.
[moderation]
enabled = true
EOF

echo "Isso configuration ready (admin dashboard enabled, moderation queue on, host=${ISSO_HOST})"
