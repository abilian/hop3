#!/bin/bash
set -e
VERSION="${HEDGEDOC_VERSION:-1.9.9}"
echo "Downloading HedgeDoc v${VERSION}..."
curl -sL "https://github.com/hedgedoc/hedgedoc/archive/refs/tags/${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p public/uploads
echo "HedgeDoc downloaded successfully"
