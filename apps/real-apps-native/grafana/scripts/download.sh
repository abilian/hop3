#!/bin/bash
set -e
VERSION="${GRAFANA_VERSION:-11.3.2}"

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Downloading Grafana v${VERSION} (linux-${ARCH})..."
curl -sL "https://dl.grafana.com/oss/release/grafana-${VERSION}.linux-${ARCH}.tar.gz" | tar xz --strip-components=1

mkdir -p data logs

echo "Grafana downloaded successfully"
