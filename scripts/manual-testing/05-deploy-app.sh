#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 5: Deploy the Application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env-manual-test"

# Load environment variables from previous step
if [ ! -f "${ENV_FILE}" ]; then
  echo "❌ Error: Environment file not found: ${ENV_FILE}"
  echo "Please run 04-create-test-app.sh first."
  exit 1
fi

source "${ENV_FILE}"

# Verify required variables
if [ -z "$APP_NAME" ] || [ -z "$APP_DIR" ] || [ -z "$HOP3_MANUAL_TEST_KEY" ]; then
  echo "❌ Error: Required environment variables not set."
  echo "APP_NAME=${APP_NAME}"
  echo "APP_DIR=${APP_DIR}"
  echo "HOP3_MANUAL_TEST_KEY=${HOP3_MANUAL_TEST_KEY}"
  exit 1
fi

# Set environment variables for the hop3 CLI
export HOP3_API_URL="ssh://hop3@localhost:2222"
export HOP3_SSH_KEY=$HOP3_MANUAL_TEST_KEY
export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"

# No need to create tarball - CLI does it automatically from directory
echo "📦 Application directory ready: $APP_DIR"

# Deploy by passing directory path (CLI creates tarball internally)
echo "🚀 Deploying application..."
hop3 deploy "$APP_NAME" "$APP_DIR"

echo "✅ Deploy command sent. The server is now building the app."
