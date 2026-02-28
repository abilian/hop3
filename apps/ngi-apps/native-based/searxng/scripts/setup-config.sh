#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Create settings directory
mkdir -p searxng

# Always create/update settings to ensure correct port binding
cat > searxng/settings.yml << EOF
use_default_settings: true

general:
  debug: false
  instance_name: "SearXNG"

server:
  port: ${PORT:-8080}
  bind_address: "${BIND_ADDRESS:-127.0.0.1}"
  secret_key: "${SEARXNG_SECRET:-$(head -c 32 /dev/urandom | base64)}"
  base_url: "${SEARXNG_BASE_URL:-http://localhost:8080}"
  limiter: false

search:
  safe_search: 0
  autocomplete: ""
  default_lang: "en"

ui:
  static_use_hash: true

enabled_plugins:
  - 'Hash plugin'
  - 'Self Information'
  - 'Tracker URL remover'
EOF

echo "SearXNG configuration ready"
