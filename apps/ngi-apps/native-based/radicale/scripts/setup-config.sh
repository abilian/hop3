#!/bin/bash
set -e
cd "$(dirname "$0")/.."

if [ ! -f config ]; then
    cat > config << EOF
[server]
hosts = 0.0.0.0:${PORT:-8080}

[auth]
type = ${RADICALE_AUTH_TYPE:-none}

[storage]
filesystem_folder = collections
EOF
fi

echo "Radicale configuration ready"
