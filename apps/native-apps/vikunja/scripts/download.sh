#!/bin/bash
set -e
VERSION="${VIKUNJA_VERSION:-0.24.6}"

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Downloading Vikunja v${VERSION} (linux-${ARCH})..."
# Vikunja 0.x uses different URL format than 1.x/2.x
curl -sL "https://dl.vikunja.io/vikunja/${VERSION}/vikunja-v${VERSION}-linux-${ARCH}-full.zip" -o vikunja.zip || \
curl -sL "https://dl.vikunja.io/vikunja/${VERSION}/vikunja-${VERSION}-linux-${ARCH}-full.zip" -o vikunja.zip
unzip -q vikunja.zip
rm vikunja.zip

# Handle both naming formats
if [ -f "vikunja-v${VERSION}-linux-${ARCH}" ]; then
    mv "vikunja-v${VERSION}-linux-${ARCH}" vikunja
elif [ -f "vikunja-${VERSION}-linux-${ARCH}" ]; then
    mv "vikunja-${VERSION}-linux-${ARCH}" vikunja
fi
chmod +x vikunja

mkdir -p files

echo "Vikunja downloaded successfully"
