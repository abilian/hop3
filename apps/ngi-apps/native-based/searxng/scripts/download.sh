#!/bin/bash
set -e
echo "Downloading SearXNG..."
curl -sL "https://github.com/searxng/searxng/archive/refs/heads/master.tar.gz" | tar xz --strip-components=1
echo "SearXNG downloaded successfully"
