#!/bin/bash
set -e
VERSION="${UPTIME_KUMA_VERSION:-1.23.11}"
echo "Downloading Uptime Kuma v${VERSION}..."
curl -sL "https://github.com/louislam/uptime-kuma/archive/refs/tags/${VERSION}.tar.gz" | tar xz --strip-components=1
mkdir -p data
echo "Uptime Kuma downloaded successfully"
