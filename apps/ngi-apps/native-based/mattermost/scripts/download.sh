#!/bin/bash
# Download pre-built Mattermost release (building from source is complex)
set -e
VERSION="${MATTERMOST_VERSION:-9.4.2}"
echo "Downloading Mattermost v${VERSION} (pre-built release)..."

# Use pre-built release instead of source (building requires complex Go+Node setup)
curl -sL "https://releases.mattermost.com/${VERSION}/mattermost-${VERSION}-linux-amd64.tar.gz" | tar xz --strip-components=1

# Create required directories
mkdir -p data logs config plugins client/plugins

echo "Mattermost downloaded successfully"
