#!/bin/bash
set -e
VERSION="${UMAMI_VERSION:-2.9.0}"
echo "Downloading Umami v${VERSION}..."
curl -sL "https://github.com/umami-software/umami/archive/refs/tags/v${VERSION}.tar.gz" | tar xz --strip-components=1
echo "Umami downloaded successfully"
