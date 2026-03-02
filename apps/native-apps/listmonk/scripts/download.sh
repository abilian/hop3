#!/bin/bash
set -e
VERSION="${LISTMONK_VERSION:-3.0.0}"

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Downloading Listmonk v${VERSION} (linux-${ARCH})..."
curl -sL "https://github.com/knadh/listmonk/releases/download/v${VERSION}/listmonk_${VERSION}_linux_${ARCH}.tar.gz" | tar xz

echo "Listmonk binary downloaded successfully"
