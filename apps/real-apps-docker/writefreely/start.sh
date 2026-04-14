#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

cd /opt/writefreely

cat > config.ini << EOF
[server]
port   = ${PORT}
bind   = 0.0.0.0
hash_seed = $(head -c 32 /dev/urandom | base64)

[database]
type     = sqlite3
filename = /data/writefreely.db

[app]
site_name  = WriteFreely
host       = http://localhost:${PORT}
theme      = write
federation = true
local_timeline = true
EOF

if [ ! -f /data/writefreely.db ]; then
    ./writefreely --init-db || true
    ./writefreely --gen-keys || true
fi

exec ./writefreely
