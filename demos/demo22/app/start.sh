#!/bin/sh
set -e

echo "==> Starting Radicale CalDAV/CardDAV Server"

# Create data directories
mkdir -p /app/data/collections

# Generate config from template
echo "==> Generating configuration"
cat > /app/config << EOF
[server]
hosts = 0.0.0.0:5232

[auth]
# For demo purposes, use htpasswd authentication
# In production, configure LDAP or other auth methods
type = htpasswd
htpasswd_filename = /app/data/htpasswd
htpasswd_encryption = bcrypt

[rights]
type = from_file
file = /app/rights

[storage]
type = multifilesystem
filesystem_folder = /app/data/collections

[web]
type = internal

[logging]
level = warning
EOF

# Create default htpasswd file if not exists
# Default user: demo / demo
if [ ! -f /app/data/htpasswd ]; then
    echo "==> Creating default user (demo/demo)"
    # bcrypt hash for "demo"
    echo 'demo:$2b$12$LQv3c1yqBWVHxkd0LHAkCO.NKHLvxhCd7C0YcY6PtFaKXBjrCPvAu' > /app/data/htpasswd
fi

echo "==> Starting Radicale on port 5232"
exec python -m radicale --config /app/config
