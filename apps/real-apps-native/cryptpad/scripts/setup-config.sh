#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Create config if not exists
mkdir -p config blob block data datastore
if [ ! -f config/config.js ]; then
    cp config/config.example.js config/config.js
fi

# Update configuration for Hop3
cat > config/config.js << EOF
module.exports = {
    httpUnsafeOrigin: '${CPAD_MAIN_DOMAIN:-http://localhost:8080}',
    httpSafeOrigin: '${CPAD_MAIN_DOMAIN:-http://localhost:8080}',
    httpAddress: '${BIND_ADDRESS:-127.0.0.1}',
    httpPort: ${PORT:-8080},

    // File storage paths
    filePath: './datastore/',
    archivePath: './data/archive',
    pinPath: './data/pins',
    taskPath: './data/tasks',
    blockPath: './block',
    blobPath: './blob',
    blobStagingPath: './data/blobstage',
    decreePath: './data/decrees',

    // Default permissions
    allowSubscriptions: false,
    defaultStorageLimit: 50 * 1024 * 1024,

    // Admin settings
    adminKeys: [],

    // Disable telemetry
    removeDonateButton: true,

    verbose: false,
};
EOF

echo "CryptPad configuration ready"
