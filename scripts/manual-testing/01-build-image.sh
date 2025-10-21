#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 1: Build the E2E Docker Image

# From your project's root directory
docker build \
  -f packages/hop3-server/tests/d_e2e/docker/Dockerfile \
  -t hop3-e2e:test \
  .

echo "✅ Docker image 'hop3-e2e:test' built successfully."
