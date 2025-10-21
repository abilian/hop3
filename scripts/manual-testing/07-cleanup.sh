#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 7: Cleanup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env-manual-test"

echo ""
echo "🧹 Cleaning up..."

# Load environment variables if available
if [ -f "${ENV_FILE}" ]; then
  source "${ENV_FILE}"
fi

# Stop and remove the container
echo "Stopping container..."
docker stop hop3-debug-container 2>/dev/null || true
docker rm hop3-debug-container 2>/dev/null || true

# Remove temporary files
if [ -n "$HOP3_MANUAL_TEST_KEY" ] && [ -f "$HOP3_MANUAL_TEST_KEY" ]; then
  echo "Removing SSH key: $HOP3_MANUAL_TEST_KEY"
  rm -f "$HOP3_MANUAL_TEST_KEY"
fi

if [ -n "$APP_DIR" ] && [ -d "$APP_DIR" ]; then
  echo "Removing app directory: $APP_DIR"
  rm -rf "$APP_DIR"
fi

# Remove environment file
if [ -f "${ENV_FILE}" ]; then
  echo "Removing environment file: ${ENV_FILE}"
  rm -f "${ENV_FILE}"
fi

echo "✅ Cleanup complete."
