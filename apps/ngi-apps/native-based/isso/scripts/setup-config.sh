#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f isso.cfg ]; then
    cat > isso.cfg << EOF
[general]
dbpath = data/comments.db
host = ${ISSO_HOST:-http://localhost:8080}

[server]
listen = http://0.0.0.0:${PORT:-8080}

[moderation]
enabled = false
EOF
fi

echo "Isso configuration ready"
