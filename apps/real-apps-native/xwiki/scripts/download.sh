#!/bin/bash
set -euo pipefail
VERSION="${XWIKI_VERSION:-16.1.0}"
URL="https://maven.xwiki.org/releases/org/xwiki/platform/xwiki-platform-distribution-jetty-hsqldb/${VERSION}/xwiki-platform-distribution-jetty-hsqldb-${VERSION}.zip"

echo "Downloading XWiki v${VERSION}..."
# Robust download (was a bare `curl -sL`, which failed silently):
#   -f  fail loud on HTTP errors — never write a 404 page into xwiki.zip;
#   -S  show the error reason (a plain -s swallowed it → empty stderr, exit 92);
#   --retry  a transient CURLE_HTTP2_STREAM (exit 92) must not be fatal;
#   --http1.1  maven.xwiki.org offers h2 but its HTTP/2 stream errored — pin 1.1.
curl -fsSL --retry 3 --retry-delay 5 --http1.1 "$URL" -o xwiki.zip

unzip -q xwiki.zip
mv "xwiki-platform-distribution-jetty-hsqldb-${VERSION}"/* .
rmdir "xwiki-platform-distribution-jetty-hsqldb-${VERSION}"
rm xwiki.zip
chmod +x start_xwiki*.sh stop_xwiki*.sh
echo "XWiki downloaded successfully"
