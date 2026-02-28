#!/bin/bash
set -e
VERSION="${ISSO_VERSION:-0.13.1.dev0}"
echo "Downloading Isso..."
curl -sL "https://github.com/isso-comments/isso/archive/refs/heads/master.tar.gz" | tar xz --strip-components=1
mkdir -p data
echo "Isso downloaded successfully"
