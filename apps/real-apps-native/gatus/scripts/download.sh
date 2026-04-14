#!/bin/bash
set -e
VERSION="${GATUS_VERSION:-5.35.0}"
URL="https://github.com/TwiN/gatus/archive/refs/tags/v${VERSION}.tar.gz"

echo "Downloading Gatus v${VERSION} source..."
curl -fsSL "$URL" | tar xz --strip-components=1
echo "Gatus source downloaded"
