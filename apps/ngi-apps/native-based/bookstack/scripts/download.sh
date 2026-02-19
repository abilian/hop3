#!/bin/bash
set -e
VERSION="${BOOKSTACK_VERSION:-24.02}"
echo "Downloading BookStack v${VERSION}..."
curl -sL "https://github.com/BookStackApp/BookStack/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p storage/app storage/framework/{cache,sessions,views} storage/logs bootstrap/cache
chmod -R 775 storage bootstrap/cache
echo "BookStack downloaded successfully"
