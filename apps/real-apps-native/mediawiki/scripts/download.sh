#!/bin/bash
# Download MediaWiki source tarball from the official Wikimedia release
# mirror. MediaWiki ships composer.json in-tree; Hop3's PHP toolchain
# will run `composer install --no-dev` as the explicit build step.
set -e
VERSION="${MEDIAWIKI_VERSION:-1.41.2}"
# Major.minor feed directory — 1.41.2 lives under .../1.41/
MAJOR_MINOR="${VERSION%.*}"
URL="https://releases.wikimedia.org/mediawiki/${MAJOR_MINOR}/mediawiki-${VERSION}.tar.gz"

echo "Downloading MediaWiki ${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1

echo "MediaWiki ${VERSION} extracted"
