#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Master script to run all E2E manual test steps sequentially

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env-manual-test"

# Function to run commands with echo
run() {
  echo ""
  echo "▶ Running: $*"
  "$@"
  local status=$?
  if [ $status -ne 0 ]; then
    echo "❌ Command failed with exit code $status: $*"
    exit $status
  fi
  return $status
}

echo "=========================================="
echo "Hop3 Manual E2E Test Suite"
echo "=========================================="
echo "Commands will be displayed as they run."
echo "Execution will stop on first error."
echo "=========================================="

# Step 1: Build image
echo ""
echo "Step 1: Building Docker image..."
run bash "${SCRIPT_DIR}/01-build-image.sh"

# Step 2: Start container
echo ""
echo "Step 2: Starting container..."
run bash "${SCRIPT_DIR}/02-start-container.sh"

# Step 3: Extract SSH key
echo ""
echo "Step 3: Extracting SSH key..."
run bash "${SCRIPT_DIR}/03-extract-ssh-key.sh"

# Export HOP3_MANUAL_TEST_KEY so subsequent scripts can use it
export HOP3_MANUAL_TEST_KEY="/tmp/hop3-debug-key"
echo "HOP3_MANUAL_TEST_KEY=${HOP3_MANUAL_TEST_KEY}" > "${ENV_FILE}"

# Step 4: Create test app
echo ""
echo "Step 4: Creating test application..."
# Create app and capture environment variables
APP_DIR="/tmp/flask-manual-test"
run rm -rf "$APP_DIR"
run mkdir -p "$APP_DIR"

echo "▶ Creating Flask app.py"
cat << 'EOF' > $APP_DIR/app.py
from flask import Flask
app = Flask(__name__)
@app.route("/")
def index():
    return "Hello from Manual E2E Test!"
EOF

echo "▶ Creating requirements.txt"
echo "flask>=3.0" > $APP_DIR/requirements.txt

echo "▶ Creating Procfile"
echo "web: flask --app app run --host 0.0.0.0 --port \$PORT" > $APP_DIR/Procfile

# Generate app name and hostname
APP_NAME="manual-app-$(date +%s)"
HOSTNAME="${APP_NAME}.test.local"
echo "▶ Creating ENV file with HOST_NAME=${HOSTNAME}"
echo "HOST_NAME=${HOSTNAME}" > $APP_DIR/ENV

# Save to environment file
echo "APP_DIR=${APP_DIR}" >> "${ENV_FILE}"
echo "APP_NAME=${APP_NAME}" >> "${ENV_FILE}"
echo "HOSTNAME=${HOSTNAME}" >> "${ENV_FILE}"

echo "✅ Test application created in: $APP_DIR"
echo "   App name: $APP_NAME"
echo "   Hostname: $HOSTNAME"

# Step 5: Deploy
echo ""
echo "Step 5: Deploying application..."

# Set environment variables for hop3 CLI
echo "▶ Setting hop3 CLI environment variables"
export HOP3_API_URL="ssh://hop3@localhost:2222"
export HOP3_SSH_KEY=$HOP3_MANUAL_TEST_KEY
export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"

# No need to create tarball - CLI does it automatically from directory
echo "📦 Application directory ready: $APP_DIR"

# Deploy by passing directory path (CLI creates tarball internally)
echo "🚀 Deploying application..."
run hop3 deploy "$APP_NAME" "$APP_DIR"

echo "✅ Deploy command sent. The server is now building the app."

# Step 6: Verify
echo ""
echo "Step 6: Verifying deployment..."
echo "🔎 Waiting for deployment to complete... (this can take ~30 seconds)"
run sleep 30

echo ""
echo "Checking application status:"
run hop3 app:status "$APP_NAME"

echo ""
echo "Checking application list:"
run hop3 apps

echo ""
echo "🔎 Verifying HTTP access through the Nginx proxy..."
echo "Sending requests to localhost:8080 with Host header '${HOSTNAME}'"

# Test with retry
echo "Pinging the app (retrying up to 10 times)..."
for i in {1..10}; do
  echo "▶ Attempt $i: curl --header \"Host: ${HOSTNAME}\" http://localhost:8080/"
  RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --header "Host: ${HOSTNAME}" http://localhost:8080/ 2>/dev/null || echo "000")
  if [ "$RESPONSE" = "200" ]; then
    echo ""
    echo "✅ SUCCESS! Received HTTP 200 OK."
    echo "Full response:"
    run curl --header "Host: ${HOSTNAME}" http://localhost:8080/
    echo ""
    break
  else
    echo "  Status: HTTP $RESPONSE. Retrying in 3 seconds..."
    sleep 3
  fi
done

if [ "$RESPONSE" != "200" ]; then
  echo ""
  echo "❌ FAILED to get a 200 response from the application."
  echo "Environment variables saved to: ${ENV_FILE}"
  echo "Run '07-cleanup.sh' to clean up when done debugging."
  exit 1
fi

echo ""
echo "=========================================="
echo "✅ All tests passed!"
echo "=========================================="
echo ""
echo "Environment variables saved to: ${ENV_FILE}"
echo "To clean up, run: bash ${SCRIPT_DIR}/07-cleanup.sh"
