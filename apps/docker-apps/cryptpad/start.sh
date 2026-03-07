#!/bin/bash
set -e

# Required environment variables - fail fast if not set
: "${PORT:?ERROR: PORT is required}"

# Optional with defaults (non-critical)
export CPAD_MAIN_DOMAIN="${CPAD_MAIN_DOMAIN:-http://localhost:${PORT}}"

# Update config.js
cat > /cryptpad/app/config/config.js << EOF
module.exports = {
    httpUnsafeOrigin: "${CPAD_MAIN_DOMAIN}",
    httpSafeOrigin: "${CPAD_SANDBOX_DOMAIN:-${CPAD_MAIN_DOMAIN}}",
    httpPort: ${PORT},
    httpAddress: "0.0.0.0",

    filePath: "/cryptpad/datastore",
    archivePath: "/cryptpad/data/archive",
    pinPath: "/cryptpad/data/pins",
    taskPath: "/cryptpad/data/tasks",
    blockPath: "/cryptpad/block",
    blobPath: "/cryptpad/blob",
    blobStagingPath: "/cryptpad/blobstage",
    decreePath: "/cryptpad/data/decrees",

    logPath: false,
    logToStdout: true,
    logLevel: "info",

    adminKeys: [],

    defaultStorageLimit: 50 * 1024 * 1024,

    installMethod: "hop3",
};
EOF

# Ensure proper ownership
chown -R cryptpad:cryptpad /cryptpad

# Run CryptPad as cryptpad user
exec su cryptpad -c "cd /cryptpad/app && node server.js"
