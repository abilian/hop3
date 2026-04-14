#!/bin/bash
set -e
VERSION="${OWNCAST_VERSION:-0.2.5}"

ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="64bit" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://github.com/owncast/owncast/releases/download/v${VERSION}/owncast-${VERSION}-linux-${ARCH}.zip"
echo "Downloading Owncast v${VERSION}..."
curl -fsSL "$URL" -o owncast.zip
unzip -o owncast.zip
rm owncast.zip
chmod +x owncast
echo "Owncast downloaded successfully"
