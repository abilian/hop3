#!/bin/bash
# Generate a minimal gatus config.yaml
set -e

mkdir -p config data

cat > config/config.yaml << EOF
storage:
  type: sqlite
  path: data/gatus.db

web:
  address: 0.0.0.0
  port: ${PORT:-8080}

endpoints:
  - name: self
    url: http://localhost:${PORT:-8080}/health
    interval: 60s
    conditions:
      - "[STATUS] == 200"
EOF

# Gatus auto-detects ./config/config.yaml relative to its CWD.
