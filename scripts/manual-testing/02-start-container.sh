#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 2: Start the Hop3 Container

# Stop and remove any previous container with the same name
docker stop hop3-debug-container >/dev/null 2>&1 || true
docker rm hop3-debug-container >/dev/null 2>&1 || true

# Run the container
docker run \
  --name hop3-debug-container \
  -d \
  -p 2222:22 \
  -p 8080:80 \
  -p 8008:8000 \
  -e HOP3_PROXY_TYPE=nginx \
  hop3-e2e:test

echo "🚀 Starting container... waiting a few seconds for services to initialize."
sleep 10 # Give supervisor time to start services

# Check that the container is running and services are up
docker exec hop3-debug-container supervisorctl status

echo "✅ Container 'hop3-debug-container' started."
echo "Ports mapping:"
echo "  - Host 2222 -> Container 22 (SSH)"
echo "  - Host 8080 -> Container 80 (HTTP Proxy)"
echo "  - Host 8008 -> Container 8000 (Hop3 API)"
