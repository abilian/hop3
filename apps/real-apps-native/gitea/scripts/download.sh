#!/bin/bash
set -e
VERSION="${GITEA_VERSION:-1.21.4}"

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Downloading Gitea v${VERSION} (linux-${ARCH})..."
curl -sL "https://dl.gitea.io/gitea/${VERSION}/gitea-${VERSION}-linux-${ARCH}" -o gitea
chmod +x gitea

# Create necessary directories
mkdir -p custom/conf data

echo "Gitea binary downloaded successfully"
