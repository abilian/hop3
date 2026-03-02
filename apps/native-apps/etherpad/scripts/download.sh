#!/bin/bash
# Download Etherpad source

set -e

ETHERPAD_VERSION="${ETHERPAD_VERSION:-2.0.3}"
DOWNLOAD_URL="https://github.com/ether/etherpad-lite/archive/refs/tags/v${ETHERPAD_VERSION}.tar.gz"

echo "Downloading Etherpad v${ETHERPAD_VERSION}..."

# Download and extract (strip the top-level directory)
curl -sL "$DOWNLOAD_URL" | tar xz --strip-components=1

echo "Etherpad source downloaded successfully"
