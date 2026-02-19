#!/bin/bash
set -e
VERSION="${MATTERMOST_VERSION:-9.4.2}"
echo "Downloading Mattermost v${VERSION}..."
curl -sL "https://github.com/mattermost/mattermost/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p bin data logs config plugins client/plugins
echo "Mattermost downloaded successfully"
