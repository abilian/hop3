#!/bin/bash
set -e
VERSION="${XWIKI_VERSION:-16.1.0}"
echo "Downloading XWiki v${VERSION}..."
curl -sL "https://maven.xwiki.org/releases/org/xwiki/platform/xwiki-platform-distribution-jetty-hsqldb/${VERSION}/xwiki-platform-distribution-jetty-hsqldb-${VERSION}.zip" -o xwiki.zip
unzip -q xwiki.zip
mv xwiki-platform-distribution-jetty-hsqldb-${VERSION}/* .
rmdir xwiki-platform-distribution-jetty-hsqldb-${VERSION}
rm xwiki.zip
chmod +x start_xwiki*.sh stop_xwiki*.sh
echo "XWiki downloaded successfully"
