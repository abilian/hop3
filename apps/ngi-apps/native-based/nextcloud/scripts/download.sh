#!/bin/bash
set -e
VERSION="${NEXTCLOUD_VERSION:-28.0.2}"
echo "Downloading Nextcloud v${VERSION}..."
curl -sL "https://download.nextcloud.com/server/releases/nextcloud-${VERSION}.tar.bz2" | tar xj --strip-components=1
mkdir -p data
chmod 750 data config
echo "Nextcloud downloaded successfully"
