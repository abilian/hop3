#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 6: Check the Deployment Status and Verify

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env-manual-test"

# Load environment variables from previous steps
if [ ! -f "${ENV_FILE}" ]; then
  echo "❌ Error: Environment file not found: ${ENV_FILE}"
  echo "Please run steps 03-05 first."
  exit 1
fi

source "${ENV_FILE}"

# Verify required variables
if [ -z "$APP_NAME" ] || [ -z "$HOSTNAME" ] || [ -z "$HOP3_MANUAL_TEST_KEY" ]; then
  echo "❌ Error: Required environment variables not set."
  echo "APP_NAME=${APP_NAME}"
  echo "HOSTNAME=${HOSTNAME}"
  echo "HOP3_MANUAL_TEST_KEY=${HOP3_MANUAL_TEST_KEY}"
  exit 1
fi

# Set environment variables for the hop3 CLI
export HOP3_API_URL="ssh://hop3@localhost:2222"
export HOP3_SSH_KEY=$HOP3_MANUAL_TEST_KEY
export HOP3_SECRET_KEY="e2e-test-secret-key-do-not-use-in-production"

echo ""
echo "🔎 Waiting for deployment to complete... (this can take ~30 seconds)"
sleep 30

echo ""
echo "Checking application status with 'hop3 app:status':"
hop3 app:status $APP_NAME || true

echo ""
echo "Checking application list with 'hop3 apps':"
hop3 apps || true

echo ""
echo "🔎 Verifying HTTP access through the Nginx proxy..."
echo "Sending requests to localhost:8080 with Host header '${HOSTNAME}'"

# Use curl to test the web endpoint. It might return a 502 error initially
# if the app's uWSGI worker hasn't started yet.
echo "Pinging the app (retrying up to 10 times)..."
for i in {1..10}; do
  RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --header "Host: ${HOSTNAME}" http://localhost:8080/ 2>/dev/null || echo "000")
  if [ "$RESPONSE" = "200" ]; then
    echo ""
    echo "✅ SUCCESS! Received HTTP 200 OK."
    echo "Full response:"
    curl --header "Host: ${HOSTNAME}" http://localhost:8080/
    echo ""
    break
  else
    echo "  Attempt $i: Received HTTP $RESPONSE. Retrying in 3 seconds..."
    sleep 3
  fi
done

if [ "$RESPONSE" != "200" ]; then
  echo ""
  echo "❌ FAILED to get a 200 response from the application."
  exit 1
fi
