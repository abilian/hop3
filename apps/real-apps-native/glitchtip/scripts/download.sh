#!/bin/bash
# GlitchTip 6.x ships PEP-621 `[project].dependencies` + `uv.lock`;
# the Python toolchain's auto-detect picks up uv.lock and runs
# `uv sync --frozen` directly. No conversion step needed here.
set -e
VERSION="${GLITCHTIP_VERSION:-6.1.5}"
URL="https://gitlab.com/glitchtip/glitchtip-backend/-/archive/v${VERSION}/glitchtip-backend-v${VERSION}.tar.gz"

echo "Downloading GlitchTip ${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1
echo "GlitchTip source downloaded"
