#!/bin/bash
set -e
VERSION="${GOTOSOCIAL_VERSION:-0.21.2}"

ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://codeberg.org/superseriousbusiness/gotosocial/releases/download/v${VERSION}/gotosocial_${VERSION}_linux_${ARCH}.tar.gz"
echo "Downloading GoToSocial v${VERSION}..."
curl -fsSL "$URL" | tar xz
echo "GoToSocial downloaded successfully"
