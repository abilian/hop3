#!/bin/bash
set -e
VERSION="${DOLIBARR_VERSION:-19.0.3}"
echo "Downloading Dolibarr v${VERSION}..."
curl -sL "https://github.com/Dolibarr/dolibarr/archive/refs/tags/${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p documents
echo "Dolibarr downloaded successfully"
