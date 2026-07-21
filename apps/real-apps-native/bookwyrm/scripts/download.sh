#!/bin/bash
# Downloads the BookWyrm source. Dependencies are NOT derived here: a
# committed, fully pinned `requirements.txt` drives the install. It was
# frozen at packaging time with `uv pip compile` from this release's
# PEP-735 `[dependency-groups].main` (+ gunicorn), resolving the full
# transitive closure to `==` pins — so the deploy installs exactly the
# recorded versions instead of re-flattening unpinned ranges (and missing
# every transitive dep) on each deploy. ADR 039: freeze at packaging time,
# in the repo, not at deploy time.
set -e
VERSION="${BOOKWYRM_VERSION:-0.8.5}"
URL="https://github.com/bookwyrm-social/bookwyrm/archive/refs/tags/v${VERSION}.tar.gz"

echo "Downloading BookWyrm v${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1

# The Python toolchain errors if both requirements.txt and pyproject.toml
# are present (a silent override is a design smell). The committed
# requirements.txt is the source of truth; move upstream's pyproject aside
# so the deployer sees a single-format tree. Upstream ships no root
# requirements.txt, so the extraction above does not clobber the committed
# one. Preserving pyproject as `.packaging-time` leaves the source inspectable.
mv pyproject.toml pyproject.toml.packaging-time

echo "BookWyrm source ready (requirements.txt is committed + pinned)"
