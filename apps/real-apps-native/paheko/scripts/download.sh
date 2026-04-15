#!/bin/bash
set -e
VERSION="${PAHEKO_VERSION:-1.3.15}"

# Paheko canonical mirror has bot-verification; use github codeload.
URL="https://codeload.github.com/paheko/paheko/tar.gz/refs/tags/${VERSION}"
echo "Downloading Paheko ${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1
echo "Paheko source downloaded"
