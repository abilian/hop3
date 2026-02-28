#!/bin/bash
set -e
VERSION="${CRYPTPAD_VERSION:-5.7.0}"
echo "Downloading CryptPad v${VERSION}..."
curl -sL "https://github.com/cryptpad/cryptpad/archive/refs/tags/${VERSION}.tar.gz" | tar xz --strip-components=1
echo "CryptPad downloaded successfully"
