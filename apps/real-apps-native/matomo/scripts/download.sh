#!/bin/bash
set -e
VERSION="${MATOMO_VERSION:-5.0.1}"
echo "Downloading Matomo v${VERSION}..."
curl -sL "https://builds.matomo.org/matomo-${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p tmp/assets tmp/cache tmp/logs tmp/tcpdf tmp/templates_c
chmod -R 775 tmp config
echo "Matomo downloaded successfully"
