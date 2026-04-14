#!/bin/bash
set -e
VERSION="${FORGEJO_VERSION:-14.0.3}"

ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Downloading Forgejo v${VERSION} (linux-${ARCH})..."
curl -fsSL "https://codeberg.org/forgejo/forgejo/releases/download/v${VERSION}/forgejo-${VERSION}-linux-${ARCH}" -o forgejo
chmod +x forgejo

mkdir -p custom/conf data
echo "Forgejo binary downloaded successfully"
