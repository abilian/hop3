#!/bin/bash
# Download Wiki.js

set -e

WIKIJS_VERSION="${WIKIJS_VERSION:-2.5.303}"
DOWNLOAD_URL="https://github.com/Requarks/wiki/releases/download/v${WIKIJS_VERSION}/wiki-js.tar.gz"

echo "Downloading Wiki.js v${WIKIJS_VERSION}..."

# Download and extract
curl -sL "$DOWNLOAD_URL" | tar xz

echo "Wiki.js downloaded successfully"
