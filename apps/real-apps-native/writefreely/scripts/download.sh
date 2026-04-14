#!/bin/bash
set -e
VERSION="${WRITEFREELY_VERSION:-0.16.0}"

ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

URL="https://github.com/writefreely/writefreely/releases/download/v${VERSION}/writefreely_${VERSION}_linux_${ARCH}.tar.gz"
echo "Downloading WriteFreely v${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1
echo "WriteFreely downloaded successfully"
