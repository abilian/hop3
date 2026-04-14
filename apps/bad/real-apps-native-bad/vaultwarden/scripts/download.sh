#!/bin/bash
# Download Vaultwarden source + web-vault assets
set -e

VAULTWARDEN_VERSION="${VAULTWARDEN_VERSION:-1.35.4}"
WEBVAULT_VERSION="${WEBVAULT_VERSION:-v2025.1.1}"

# Source tarball: Rust toolchain will compile with cargo build --release
SRC_URL="https://github.com/dani-garcia/vaultwarden/archive/refs/tags/${VAULTWARDEN_VERSION}.tar.gz"
echo "Downloading Vaultwarden source ${VAULTWARDEN_VERSION}..."
curl -fsSL "$SRC_URL" | tar xz --strip-components=1

# Pre-built web-vault assets from the companion repo.
WEBVAULT_URL="https://github.com/dani-garcia/bw_web_builds/releases/download/${WEBVAULT_VERSION}/bw_web_${WEBVAULT_VERSION}.tar.gz"
echo "Downloading web-vault ${WEBVAULT_VERSION}..."
mkdir -p web-vault
curl -fsSL "$WEBVAULT_URL" | tar xz -C web-vault --strip-components=1

echo "Vaultwarden source + web-vault ready"
