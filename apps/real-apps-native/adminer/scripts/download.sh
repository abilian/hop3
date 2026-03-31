#!/bin/bash
set -e
VERSION="${ADMINER_VERSION:-4.8.1}"
echo "Downloading Adminer v${VERSION}..."
curl -sL "https://github.com/vrana/adminer/releases/download/v${VERSION}/adminer-${VERSION}.php" -o index.php
echo "Adminer downloaded successfully"
