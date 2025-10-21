#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Step 3: Extract the SSH Key for CLI Access

# Define the path for the temporary SSH key
export HOP3_MANUAL_TEST_KEY="/tmp/hop3-debug-key"

# Extract the key from the container and save it locally
docker exec hop3-debug-container cat /home/hop3/.ssh/id_rsa > $HOP3_MANUAL_TEST_KEY

# Set the correct file permissions (this is critical)
chmod 600 $HOP3_MANUAL_TEST_KEY

echo "🔑 SSH key extracted to: $HOP3_MANUAL_TEST_KEY"
