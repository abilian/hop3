#!/bin/bash
set -e
VERSION="${MONICA_VERSION:-4.0.0}"
echo "Downloading Monica v${VERSION}..."
curl -sL "https://github.com/monicahq/monica/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p storage/app storage/framework/{cache,sessions,views} storage/logs bootstrap/cache
chmod -R 775 storage bootstrap/cache
echo "Monica downloaded successfully"
