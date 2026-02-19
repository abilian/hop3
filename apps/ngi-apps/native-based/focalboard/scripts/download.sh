#!/bin/bash
set -e
VERSION="${FOCALBOARD_VERSION:-7.10.5}"
echo "Downloading Focalboard v${VERSION}..."
curl -sL "https://github.com/mattermost-community/focalboard/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p bin
echo "Focalboard downloaded successfully"
