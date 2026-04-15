#!/bin/bash
# Downloads BookWyrm and emits a flat `requirements.txt` from its
# PEP-735 `[dependency-groups].main`. Upstream ships only a pyproject
# with dependency-groups and no uv.lock, which pip cannot consume
# directly. Per ADR 039, packaging-time freezing is the right place
# for this conversion. Uses pure-Python tomllib (stdlib in 3.11+) so
# no extra tooling is required on the packaging host.
set -e
VERSION="${BOOKWYRM_VERSION:-0.8.5}"
URL="https://github.com/bookwyrm-social/bookwyrm/archive/refs/tags/v${VERSION}.tar.gz"

echo "Downloading BookWyrm v${VERSION}..."
curl -fsSL "$URL" | tar xz --strip-components=1

python3 - <<'PY'
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Python < 3.11
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
deps = data.get("dependency-groups", {}).get("main", [])
with open("requirements.txt", "w") as out:
    for dep in deps:
        if isinstance(dep, str):
            out.write(dep + "\n")
    out.write("gunicorn\n")
print(f"Wrote {len([d for d in deps if isinstance(d, str)]) + 1} deps to requirements.txt")
PY

echo "BookWyrm source + requirements.txt ready"
