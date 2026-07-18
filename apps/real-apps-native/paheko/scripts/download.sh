#!/bin/bash
set -e
VERSION="${PAHEKO_VERSION:-1.3.15}"

# Download the official Paheko RELEASE tarball (fossil "unversioned" storage).
# The release bundles the KD2 framework (include/lib/KD2) and modules/ — the
# GitHub *source* tag does NOT include them (KD2 is a vendored external fetched
# at build time), so a source checkout fatals on every request with
# "Failed opening required .../KD2/ErrorManager.php".
URL="https://fossil.kd2.org/paheko/uv/paheko-${VERSION}.tar.gz"
echo "Downloading Paheko ${VERSION} (release tarball)..."
curl -fsSL "$URL" | tar xz --strip-components=1
echo "Paheko ${VERSION} downloaded"

# Fail loud if the bundled framework is missing, rather than deploying a tree
# that would 500 on the first request.
if [ ! -f include/lib/KD2/ErrorManager.php ]; then
    echo "Paheko download failed: KD2 framework missing (include/lib/KD2). Aborting." >&2
    exit 1
fi
