#!/bin/bash
set -e
VERSION="${INVOICE_NINJA_VERSION:-5.8.37}"
echo "Downloading Invoice Ninja v${VERSION}..."
curl -sL "https://github.com/invoiceninja/invoiceninja/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p storage/app storage/framework/{cache,sessions,views} storage/logs bootstrap/cache public/storage
chmod -R 775 storage bootstrap/cache public/storage
echo "Invoice Ninja downloaded successfully"
