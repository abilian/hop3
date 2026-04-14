#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

cd /opt/gatus

cat > config/config.yaml << EOF
storage:
  type: sqlite
  path: /data/gatus.db

web:
  address: 0.0.0.0
  port: ${PORT}

endpoints:
  - name: self
    url: http://localhost:${PORT}/health
    interval: 60s
    conditions:
      - "[STATUS] == 200"
EOF

exec /usr/local/bin/gatus
