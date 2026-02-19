#!/bin/bash
# Download Ghost

set -e

GHOST_VERSION="${GHOST_VERSION:-5.74.5}"

echo "Downloading Ghost v${GHOST_VERSION}..."

# Install ghost-cli globally
npm install -g ghost-cli

# Install Ghost locally
ghost install local --no-start --no-setup --dir .

echo "Ghost downloaded successfully"
